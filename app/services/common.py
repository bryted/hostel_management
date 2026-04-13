from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import date, datetime, timezone
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bed, Block, Floor, Room

DEFAULT_BASE_CURRENCY = "GHS"
FALLBACK_CURRENCIES = ("GHS", "USD")


def as_decimal(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value))


def combine_date(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)


def normalize_phone(value: str) -> str:
    text = (value or "").strip().replace(" ", "").replace("-", "")
    if text.startswith("+"):
        text = text[1:]
    if text.startswith("00"):
        text = text[2:]
    if text.startswith("0") and len(text) == 10:
        text = f"233{text[1:]}"
    return text


def validate_phone(value: str) -> tuple[bool, str, str]:
    if not value or not value.strip():
        return True, "", ""
    normalized = normalize_phone(value)
    if not normalized.isdigit():
        return False, "", "Phone must contain digits only."
    if normalized.startswith("233"):
        if len(normalized) != 12:
            return (
                False,
                "",
                "Phone must be in Ghana format: 0XXXXXXXXX or 233XXXXXXXXX (no +).",
            )
    elif len(normalized) < 9 or len(normalized) > 15:
        return False, "", "Phone must be in international format, e.g., 233559448237."
    return True, normalized, ""


def get_base_currency() -> str:
    candidate = (os.getenv("BASE_CURRENCY") or DEFAULT_BASE_CURRENCY).strip().upper()
    if len(candidate) != 3 or not candidate.isalpha():
        return DEFAULT_BASE_CURRENCY
    return candidate


def currency_options() -> list[str]:
    base = get_base_currency()
    options = [base]
    for code in FALLBACK_CURRENCIES:
        if code not in options:
            options.append(code)
    return options


def format_money(value: Decimal | float | int, currency: str | None = None) -> str:
    currency = (currency or get_base_currency()).upper()
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    return f"{currency} {amount:,.2f}"


def operational_inventory_predicate(
    room_model: type[Room] = Room,
    block_model: type[Block] = Block,
    floor_model: type[Floor] = Floor,
):
    return sa.and_(
        room_model.is_active.is_(True),
        block_model.is_active.is_(True),
        sa.or_(room_model.floor_id.is_(None), floor_model.is_active.is_(True)),
    )


def select_operational_bed_rows(*, statuses: Sequence[str] | None = ("AVAILABLE",)):
    query = (
        select(Bed, Room, Floor, Block)
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .where(operational_inventory_predicate(Room, Block, Floor))
    )
    if statuses is not None:
        query = query.where(Bed.status.in_(tuple(statuses)))
    return query


def bed_is_in_operational_inventory(session: Session, bed_id: int) -> bool:
    return (
        session.execute(
            select(Bed.id)
            .join(Room, Room.id == Bed.room_id)
            .join(Block, Block.id == Room.block_id)
            .outerjoin(Floor, Floor.id == Room.floor_id)
            .where(Bed.id == bed_id, operational_inventory_predicate(Room, Block, Floor))
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )
