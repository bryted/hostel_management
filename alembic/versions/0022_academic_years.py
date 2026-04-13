"""add academic year support

Revision ID: 0022_academic_years
Revises: 0021_search_performance_indexes
Create Date: 2026-04-13 02:10:00.000000
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0022_academic_years"
down_revision = "0021_search_performance_indexes"
branch_labels = None
depends_on = None


def _academic_year_start_month() -> int:
    raw = (os.getenv("ACADEMIC_YEAR_START_MONTH") or "").strip()
    if not raw:
        return 9
    try:
        month = int(raw)
    except ValueError:
        return 9
    return month if 1 <= month <= 12 else 9


def _normalize_date(value: object | None) -> date:
    if value is None:
        return datetime.now(timezone.utc).date()
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).date()
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.now(timezone.utc).date()


def _academic_year_bounds(target: date) -> tuple[date, date, str]:
    start_month = _academic_year_start_month()
    start_year = target.year if target.month >= start_month else target.year - 1
    start_date = date(start_year, start_month, 1)
    end_year = start_year + 1
    end_month = start_month - 1 or 12
    end_month_year = end_year if start_month > 1 else start_year
    if end_month == 2:
        is_leap = end_month_year % 4 == 0 and (end_month_year % 100 != 0 or end_month_year % 400 == 0)
        end_day = 29 if is_leap else 28
    elif end_month in {4, 6, 9, 11}:
        end_day = 30
    else:
        end_day = 31
    end_date = date(end_month_year, end_month, end_day)
    return start_date, end_date, f"{start_year}/{start_year + 1}"


def _year_id_for_date(bind, cache: dict[str, int], value: object | None) -> int:
    start_date, end_date, label = _academic_year_bounds(_normalize_date(value))
    if label in cache:
        return cache[label]
    existing_id = bind.execute(
        sa.text("SELECT id FROM academic_years WHERE label = :label LIMIT 1"),
        {"label": label},
    ).scalar_one_or_none()
    if existing_id is None:
        existing_id = bind.execute(
            sa.text(
                """
                INSERT INTO academic_years (label, start_date, end_date, is_current, is_closed)
                VALUES (:label, :start_date, :end_date, false, false)
                RETURNING id
                """
            ),
            {"label": label, "start_date": start_date, "end_date": end_date},
        ).scalar_one()
    cache[label] = int(existing_id)
    return int(existing_id)


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "academic_years",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True, nullable=False),
        sa.Column("label", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("label", name="uq_academic_years_label"),
    )
    op.create_index("ix_academic_years_is_current", "academic_years", ["is_current"], unique=False)
    op.create_index("ix_academic_years_start_end", "academic_years", ["start_date", "end_date"], unique=False)

    for table_name in ("invoices", "payments", "receipts", "bed_reservations", "allocations"):
        op.add_column(table_name, sa.Column("academic_year_id", sa.BigInteger(), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table_name}_academic_year_id_academic_years"),
            table_name,
            "academic_years",
            ["academic_year_id"],
            ["id"],
        )

    op.create_index("ix_invoices_academic_year_id_status", "invoices", ["academic_year_id", "status"], unique=False)
    op.create_index("ix_payments_academic_year_id_paid_at", "payments", ["academic_year_id", "paid_at"], unique=False)
    op.create_index("ix_receipts_academic_year_id_issued_at", "receipts", ["academic_year_id", "issued_at"], unique=False)
    op.create_index("ix_bed_reservations_academic_year_id", "bed_reservations", ["academic_year_id"], unique=False)
    op.create_index("ix_allocations_academic_year_id", "allocations", ["academic_year_id"], unique=False)

    cache: dict[str, int] = {}

    invoice_rows = bind.execute(
        sa.text("SELECT id, COALESCE(due_at, issued_at, created_at) AS anchor_at FROM invoices")
    ).mappings()
    for row in invoice_rows:
        bind.execute(
            sa.text("UPDATE invoices SET academic_year_id = :academic_year_id WHERE id = :row_id"),
            {"academic_year_id": _year_id_for_date(bind, cache, row["anchor_at"]), "row_id": row["id"]},
        )

    payment_rows = bind.execute(
        sa.text(
            """
            SELECT payments.id, payments.invoice_id, payments.paid_at, payments.created_at, invoices.academic_year_id AS invoice_year_id
            FROM payments
            LEFT JOIN invoices ON invoices.id = payments.invoice_id
            """
        )
    ).mappings()
    for row in payment_rows:
        academic_year_id = row["invoice_year_id"] or _year_id_for_date(bind, cache, row["paid_at"] or row["created_at"])
        bind.execute(
            sa.text("UPDATE payments SET academic_year_id = :academic_year_id WHERE id = :row_id"),
            {"academic_year_id": academic_year_id, "row_id": row["id"]},
        )

    receipt_rows = bind.execute(
        sa.text(
            """
            SELECT receipts.id, receipts.payment_id, receipts.issued_at, receipts.created_at, payments.academic_year_id AS payment_year_id
            FROM receipts
            LEFT JOIN payments ON payments.id = receipts.payment_id
            """
        )
    ).mappings()
    for row in receipt_rows:
        academic_year_id = row["payment_year_id"] or _year_id_for_date(bind, cache, row["issued_at"] or row["created_at"])
        bind.execute(
            sa.text("UPDATE receipts SET academic_year_id = :academic_year_id WHERE id = :row_id"),
            {"academic_year_id": academic_year_id, "row_id": row["id"]},
        )

    reservation_rows = bind.execute(
        sa.text(
            """
            SELECT bed_reservations.id, bed_reservations.invoice_id, bed_reservations.reserved_at, bed_reservations.created_at, invoices.academic_year_id AS invoice_year_id
            FROM bed_reservations
            LEFT JOIN invoices ON invoices.id = bed_reservations.invoice_id
            """
        )
    ).mappings()
    for row in reservation_rows:
        academic_year_id = row["invoice_year_id"] or _year_id_for_date(bind, cache, row["reserved_at"] or row["created_at"])
        bind.execute(
            sa.text("UPDATE bed_reservations SET academic_year_id = :academic_year_id WHERE id = :row_id"),
            {"academic_year_id": academic_year_id, "row_id": row["id"]},
        )

    allocation_rows = bind.execute(
        sa.text(
            """
            SELECT allocations.id, allocations.invoice_id, allocations.start_date, allocations.created_at, invoices.academic_year_id AS invoice_year_id
            FROM allocations
            LEFT JOIN invoices ON invoices.id = allocations.invoice_id
            """
        )
    ).mappings()
    for row in allocation_rows:
        academic_year_id = row["invoice_year_id"] or _year_id_for_date(bind, cache, row["start_date"] or row["created_at"])
        bind.execute(
            sa.text("UPDATE allocations SET academic_year_id = :academic_year_id WHERE id = :row_id"),
            {"academic_year_id": academic_year_id, "row_id": row["id"]},
        )

    current_id = _year_id_for_date(bind, cache, date.today())
    bind.execute(sa.text("UPDATE academic_years SET is_current = false"))
    bind.execute(
        sa.text("UPDATE academic_years SET is_current = true WHERE id = :current_id"),
        {"current_id": current_id},
    )


def downgrade() -> None:
    op.drop_index("ix_allocations_academic_year_id", table_name="allocations")
    op.drop_index("ix_bed_reservations_academic_year_id", table_name="bed_reservations")
    op.drop_index("ix_receipts_academic_year_id_issued_at", table_name="receipts")
    op.drop_index("ix_payments_academic_year_id_paid_at", table_name="payments")
    op.drop_index("ix_invoices_academic_year_id_status", table_name="invoices")

    for table_name in ("allocations", "bed_reservations", "receipts", "payments", "invoices"):
        op.drop_constraint(op.f(f"fk_{table_name}_academic_year_id_academic_years"), table_name, type_="foreignkey")
        op.drop_column(table_name, "academic_year_id")

    op.drop_index("ix_academic_years_start_end", table_name="academic_years")
    op.drop_index("ix_academic_years_is_current", table_name="academic_years")
    op.drop_table("academic_years")
