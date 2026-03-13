from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Allocation,
    Bed,
    BedEvent,
    BedReservation,
    Block,
    Floor,
    Invoice,
    InvoiceEvent,
    InvoiceItem,
    Room,
)
from app.services.common import as_decimal
from app.services.invoicing import InvoiceValidationError, update_invoice_totals
from app.services.types import InventoryRow, RepriceResult, RoomUpdateResult, UploadResult

ROOM_TYPE_TO_BEDS: dict[str, int] = {
    "1_IN_ROOM": 1,
    "2_IN_ROOM": 2,
    "3_IN_ROOM": 3,
    "4_IN_ROOM": 4,
}
UNPAID_INVOICE_STATUSES = ("draft", "submitted", "approved", "partially_paid")


def _normalize_room_type(value: str) -> str:
    raw = (value or "").strip().upper().replace("-", "_").replace(" ", "_")
    direct = {
        "1": "1_IN_ROOM",
        "2": "2_IN_ROOM",
        "3": "3_IN_ROOM",
        "4": "4_IN_ROOM",
        "1_IN_ROOM": "1_IN_ROOM",
        "2_IN_ROOM": "2_IN_ROOM",
        "3_IN_ROOM": "3_IN_ROOM",
        "4_IN_ROOM": "4_IN_ROOM",
    }
    normalized = direct.get(raw)
    if normalized is None:
        raise ValueError("room_type must be one of: 1_IN_ROOM, 2_IN_ROOM, 3_IN_ROOM, 4_IN_ROOM.")
    return normalized


def _log_bed_event(
    session: Session,
    *,
    bed_id: int,
    event_type: str,
    user_id: int | None,
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        BedEvent(
            bed_id=bed_id,
            event_type=event_type,
            user_id=user_id,
            detail_json=detail,
        )
    )


def ensure_beds_for_room(
    session: Session,
    room: Room,
    new_count: int,
    user_id: int | None,
) -> tuple[bool, str]:
    beds = (
        session.execute(select(Bed).where(Bed.room_id == room.id).order_by(Bed.bed_number))
        .scalars()
        .all()
    )
    bed_by_number = {bed.bed_number: bed for bed in beds}
    blocked = [
        bed
        for bed in beds
        if bed.bed_number > new_count and bed.status not in ("AVAILABLE", "OUT_OF_SERVICE")
    ]
    if blocked:
        labels = ", ".join(f"Bed {bed.bed_number} ({bed.status})" for bed in blocked)
        return False, f"Cannot reduce beds for room {room.room_code}; in-use beds: {labels}"

    for number in range(1, new_count + 1):
        bed = bed_by_number.get(number)
        if bed:
            if bed.status == "OUT_OF_SERVICE":
                bed.status = "AVAILABLE"
                bed.bed_label = f"Bed {number}"
                _log_bed_event(
                    session,
                    bed_id=bed.id,
                    event_type="BED_REACTIVATED",
                    user_id=user_id,
                    detail={"source": "room_setup"},
                )
            elif not bed.bed_label:
                bed.bed_label = f"Bed {number}"
            continue

        bed = Bed(
            room_id=room.id,
            bed_number=number,
            bed_label=f"Bed {number}",
            status="AVAILABLE",
        )
        session.add(bed)
        session.flush()
        _log_bed_event(
            session,
            bed_id=bed.id,
            event_type="BED_CREATED",
            user_id=user_id,
            detail={"source": "room_setup"},
        )

    for bed in beds:
        if bed.bed_number > new_count and bed.status == "AVAILABLE":
            bed.status = "OUT_OF_SERVICE"
            _log_bed_event(
                session,
                bed_id=bed.id,
                event_type="BED_DEACTIVATED",
                user_id=user_id,
                detail={"reason": "beds_count_reduced"},
            )

    room.beds_count = new_count
    return True, ""


def _upsert_invoice_item_for_room_price(session: Session, invoice: Invoice, room: Room, bed: Bed) -> None:
    description = f"{room.room_code} {bed.bed_label} - Annual bed fee"
    unit_price = as_decimal(room.unit_price_per_bed)
    item = (
        session.execute(
            select(InvoiceItem)
            .where(InvoiceItem.invoice_id == invoice.id)
            .order_by(InvoiceItem.line_no.asc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if item is None:
        item = InvoiceItem(
            invoice_id=invoice.id,
            line_no=1,
            description=description,
            quantity=Decimal("1"),
            unit_price=unit_price,
            amount=unit_price,
        )
        session.add(item)
    else:
        item.description = description
        item.quantity = Decimal("1")
        item.unit_price = unit_price
        item.amount = unit_price

    update_invoice_totals(
        invoice=invoice,
        subtotal=unit_price,
        tax=as_decimal(invoice.tax),
        discount=as_decimal(invoice.discount),
    )


def reprice_unpaid_invoices_for_room(
    session: Session,
    room_id: int,
    user_id: int,
    now: datetime,
) -> RepriceResult:
    bed_ids = session.execute(select(Bed.id).where(Bed.room_id == room_id)).scalars().all()
    if not bed_ids:
        return RepriceResult(invoices_updated=0)

    invoices = (
        session.execute(
            select(Invoice)
            .where(
                Invoice.reserved_bed_id.in_(bed_ids),
                Invoice.status.in_(UNPAID_INVOICE_STATUSES),
            )
            .order_by(Invoice.id.asc())
        )
        .scalars()
        .all()
    )
    if not invoices:
        return RepriceResult(invoices_updated=0)

    room = session.get(Room, room_id)
    if room is None:
        return RepriceResult(invoices_updated=0)

    updated = 0
    for invoice in invoices:
        if invoice.reserved_bed_id is None:
            continue
        bed = session.get(Bed, invoice.reserved_bed_id)
        if bed is None:
            continue
        _upsert_invoice_item_for_room_price(session, invoice, room, bed)
        session.add(
            InvoiceEvent(
                invoice_id=invoice.id,
                event_type="INVOICE_REPRICED_FROM_ROOM_UPDATE",
                payload={
                    "user_id": user_id,
                    "room_id": room.id,
                    "room_code": room.room_code,
                    "unit_price_per_bed": str(room.unit_price_per_bed),
                    "at": now.isoformat(),
                },
            )
        )
        updated += 1
    return RepriceResult(invoices_updated=updated)


def _resolve_block(session: Session, block_name: str) -> Block:
    block = session.execute(select(Block).where(Block.name == block_name)).scalar_one_or_none()
    if block is None:
        block = Block(name=block_name, is_active=True)
        session.add(block)
        session.flush()
    return block


def _resolve_floor(session: Session, block_id: int, floor_label: str) -> Floor:
    floor = session.execute(
        select(Floor).where(Floor.block_id == block_id, Floor.floor_label == floor_label)
    ).scalar_one_or_none()
    if floor is None:
        floor = Floor(block_id=block_id, floor_label=floor_label, is_active=True)
        session.add(floor)
        session.flush()
    return floor


def create_room_with_beds(session: Session, payload: dict[str, Any], user_id: int) -> Room:
    room_type = _normalize_room_type(str(payload["room_type"]))
    beds_count = ROOM_TYPE_TO_BEDS[room_type]
    unit_price = as_decimal(payload["unit_price_per_bed"])
    if unit_price < Decimal("0"):
        raise ValueError("unit_price_per_bed cannot be negative.")

    block_id = int(payload["block_id"])
    floor_id = int(payload["floor_id"])
    room_code = str(payload["room_code"]).strip()
    if not room_code:
        raise ValueError("room_code is required.")

    existing = session.execute(
        select(Room).where(Room.block_id == block_id, Room.room_code == room_code)
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("Room already exists in this block.")

    room = Room(
        block_id=block_id,
        floor_id=floor_id,
        room_code=room_code,
        room_type=room_type,
        beds_count=beds_count,
        unit_price_per_bed=unit_price,
        is_active=bool(payload.get("is_active", True)),
    )
    session.add(room)
    session.flush()
    ok, error = ensure_beds_for_room(session, room, beds_count, user_id)
    if not ok:
        raise ValueError(error)
    return room


def update_room_with_effects(
    session: Session,
    room_id: int,
    payload: dict[str, Any],
    user_id: int,
    now: datetime,
) -> RoomUpdateResult:
    room = session.get(Room, room_id)
    if room is None:
        raise ValueError("Room not found.")

    previous = {
        "block_id": room.block_id,
        "floor_id": room.floor_id,
        "room_code": room.room_code,
        "room_type": room.room_type,
        "beds_count": int(room.beds_count),
        "unit_price_per_bed": as_decimal(room.unit_price_per_bed),
        "is_active": bool(room.is_active),
    }

    room_type = _normalize_room_type(str(payload["room_type"]))
    new_beds = ROOM_TYPE_TO_BEDS[room_type]
    room.block_id = int(payload["block_id"])
    room.floor_id = int(payload["floor_id"])
    room.room_code = str(payload["room_code"]).strip()
    room.room_type = room_type
    room.unit_price_per_bed = as_decimal(payload["unit_price_per_bed"])
    room.is_active = bool(payload.get("is_active", True))

    if room.unit_price_per_bed < Decimal("0"):
        raise InvoiceValidationError("Unit price cannot be negative.")
    conflict = session.execute(
        select(Room.id)
        .where(Room.block_id == room.block_id, Room.room_code == room.room_code, Room.id != room.id)
        .limit(1)
    ).scalar_one_or_none()
    if conflict is not None:
        raise ValueError("Another room with this code already exists in the selected block.")

    ok, error = ensure_beds_for_room(session, room, new_beds, user_id)
    if not ok:
        raise ValueError(error)

    room_code_changed = previous["room_code"] != room.room_code
    bed_count_changed = int(previous["beds_count"]) != int(room.beds_count)
    room_type_changed = (previous["room_type"] or "") != room.room_type
    price_changed = as_decimal(previous["unit_price_per_bed"]) != as_decimal(room.unit_price_per_bed)

    repriced = 0
    if price_changed or room_code_changed or bed_count_changed:
        repriced = reprice_unpaid_invoices_for_room(session, room.id, user_id, now).invoices_updated

    return RoomUpdateResult(
        room_id=room.id,
        repriced_invoices=repriced,
        room_code_changed=room_code_changed,
        room_type_changed=room_type_changed,
        bed_count_changed=bed_count_changed,
    )


def parse_inventory_upload(df: pd.DataFrame) -> tuple[list[InventoryRow], list[str]]:
    required = ["block", "floor", "room_code", "room_type", "unit_price_per_bed"]
    normalized = {str(c).strip().lower(): c for c in df.columns}
    missing = [col for col in required if col not in normalized]
    if missing:
        return [], [f"Missing required columns: {', '.join(missing)}"]

    rows: list[InventoryRow] = []
    errors: list[str] = []
    for idx, raw in df.iterrows():
        line_no = idx + 2
        block_name = str(raw[normalized["block"]]).strip()
        floor_label = str(raw[normalized["floor"]]).strip()
        room_code = str(raw[normalized["room_code"]]).strip()
        room_type_raw = str(raw[normalized["room_type"]]).strip()
        active = True
        if "is_active" in normalized:
            active_text = str(raw[normalized["is_active"]]).strip().lower()
            active = active_text in {"1", "true", "yes", "y", "active"}
        try:
            room_type = _normalize_room_type(room_type_raw)
        except Exception:
            errors.append(
                f"Row {line_no}: room_type must be one of 1_IN_ROOM, 2_IN_ROOM, 3_IN_ROOM, 4_IN_ROOM."
            )
            continue
        beds_count = ROOM_TYPE_TO_BEDS[room_type]
        try:
            unit_price = as_decimal(raw[normalized["unit_price_per_bed"]])
        except Exception:
            errors.append(f"Row {line_no}: unit_price_per_bed must be numeric.")
            continue
        if not block_name:
            errors.append(f"Row {line_no}: block is required.")
            continue
        if not floor_label:
            errors.append(f"Row {line_no}: floor is required.")
            continue
        if not room_code:
            errors.append(f"Row {line_no}: room_code is required.")
            continue
        if unit_price < Decimal("0"):
            errors.append(f"Row {line_no}: unit_price_per_bed cannot be negative.")
            continue
        if "beds_count" in normalized and pd.notna(raw[normalized["beds_count"]]):
            try:
                input_beds = int(raw[normalized["beds_count"]])
                if input_beds != beds_count:
                    errors.append(
                        f"Row {line_no}: beds_count ({input_beds}) does not match room_type ({beds_count})."
                    )
                    continue
            except Exception:
                errors.append(f"Row {line_no}: beds_count must be an integer when provided.")
                continue
        rows.append(
            InventoryRow(
                block=block_name,
                floor=floor_label,
                room_code=room_code,
                room_type=room_type,
                beds_count=beds_count,
                unit_price_per_bed=unit_price,
                is_active=active,
            )
        )
    return rows, errors


def parse_inventory_upload_file(
    file_name: str,
    file_bytes: bytes,
) -> tuple[pd.DataFrame | None, str | None]:
    if not file_bytes:
        return None, "File is empty."
    name = (file_name or "").lower()
    buffer = io.BytesIO(file_bytes)
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(buffer)
        elif name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(buffer)
        else:
            return None, "Supported formats: .xlsx, .xls, .csv"
    except Exception as exc:
        return None, f"Could not read upload: {exc}"
    if df.empty:
        return None, "File is empty."
    return df, None


def room_bed_integrity_rows(session: Session) -> list[dict[str, Any]]:
    rooms = (
        session.execute(
            select(Room, Block, Floor)
            .join(Block, Block.id == Room.block_id)
            .outerjoin(Floor, Floor.id == Room.floor_id)
            .order_by(Block.name, Floor.floor_label, Room.room_code)
        )
        .all()
    )
    rows: list[dict[str, Any]] = []
    for room, block, floor in rooms:
        total_beds = session.execute(
            select(sa.func.count(Bed.id)).where(Bed.room_id == room.id)
        ).scalar_one()
        reserved_count = session.execute(
            select(sa.func.count(BedReservation.id)).where(
                BedReservation.status == "ACTIVE",
                BedReservation.bed_id.in_(select(Bed.id).where(Bed.room_id == room.id)),
            )
        ).scalar_one()
        confirmed_allocations = session.execute(
            select(sa.func.count(Allocation.id)).where(
                Allocation.status == "CONFIRMED",
                Allocation.bed_id.in_(select(Bed.id).where(Bed.room_id == room.id)),
            )
        ).scalar_one()
        reserved_without_reservation = session.execute(
            select(sa.func.count(Bed.id)).where(
                Bed.room_id == room.id,
                Bed.status == "RESERVED",
                ~sa.exists(
                    select(BedReservation.id).where(
                        BedReservation.bed_id == Bed.id,
                        BedReservation.status == "ACTIVE",
                    )
                ),
            )
        ).scalar_one()
        occupied_without_allocation = session.execute(
            select(sa.func.count(Bed.id)).where(
                Bed.room_id == room.id,
                Bed.status == "OCCUPIED",
                ~sa.exists(
                    select(Allocation.id).where(
                        Allocation.bed_id == Bed.id,
                        Allocation.status == "CONFIRMED",
                    )
                ),
            )
        ).scalar_one()
        issue_list: list[str] = []
        expected = ROOM_TYPE_TO_BEDS.get((room.room_type or "").upper())
        if room.floor_id is None:
            issue_list.append("missing floor")
        if expected is None or int(expected) != int(room.beds_count or 0):
            issue_list.append("room_type/beds_count mismatch")
        if int(total_beds or 0) != int(room.beds_count or 0):
            issue_list.append("beds_count mismatch")
        if int(confirmed_allocations or 0) > int(total_beds or 0):
            issue_list.append("too many allocations")
        if int(reserved_count or 0) > int(total_beds or 0):
            issue_list.append("too many reservations")
        if int(reserved_without_reservation or 0) > 0:
            issue_list.append("reserved without active reservation")
        if int(occupied_without_allocation or 0) > 0:
            issue_list.append("occupied without confirmed allocation")
        rows.append(
            {
                "Block": block.name,
                "Floor": floor.floor_label if floor else "",
                "Room": room.room_code,
                "Room type": room.room_type or "",
                "Configured beds": int(room.beds_count or 0),
                "Actual beds": int(total_beds or 0),
                "Active reservations": int(reserved_count or 0),
                "Active allocations": int(confirmed_allocations or 0),
                "Reserved w/o reservation": int(reserved_without_reservation or 0),
                "Occupied w/o allocation": int(occupied_without_allocation or 0),
                "Status": "OK" if not issue_list else "CHECK",
                "Issues": ", ".join(issue_list),
            }
        )
    return rows


def apply_inventory_rows(
    session: Session,
    rows: list[InventoryRow],
    user_id: int,
    mode: str = "upsert",
) -> UploadResult:
    if mode != "upsert":
        raise ValueError("Only upsert mode is supported.")

    result = UploadResult(created_rooms=0, updated_rooms=0)
    now = datetime.now(timezone.utc)
    for row in rows:
        block = _resolve_block(session, row.block)
        floor = _resolve_floor(session, block.id, row.floor)
        room = session.execute(
            select(Room).where(Room.block_id == block.id, Room.room_code == row.room_code)
        ).scalar_one_or_none()
        payload = {
            "block_id": block.id,
            "floor_id": floor.id,
            "room_code": row.room_code,
            "room_type": row.room_type,
            "unit_price_per_bed": row.unit_price_per_bed,
            "is_active": row.is_active,
        }
        if room is None:
            create_room_with_beds(session, payload, user_id)
            result.created_rooms += 1
            continue

        update_room_with_effects(session, room.id, payload, user_id, now)
        result.updated_rooms += 1
    return result
