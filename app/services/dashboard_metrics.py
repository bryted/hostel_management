from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, Bed, BedReservation, Block, Floor, Invoice, Payment, Receipt, Room, Tenant
from app.services.onboarding import get_onboarding_pipeline
from app.services.reservations import expired_hold_invoice_ids_query
from app.services.types import (
    AlertSnapshot,
    DashboardSnapshot,
    FinanceSnapshot,
    OccupancySnapshot,
)

UNPAID_INVOICE_STATUSES = ("draft", "submitted", "approved", "partially_paid")


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _paid_totals_subquery() -> sa.Subquery:
    return (
        select(
            Payment.invoice_id.label("invoice_id"),
            sa.func.coalesce(sa.func.sum(Payment.amount), 0).label("paid_total"),
        )
        .where(Payment.status != "voided")
        .group_by(Payment.invoice_id)
        .subquery()
    )


def get_dashboard_snapshot(
    session: Session,
    as_of: datetime,
    currency: str = "GHS",
    start_date: date | None = None,
    end_date: date | None = None,
    block_id: int | None = None,
    floor_id: int | None = None,
    include_occupancy_tables: bool = True,
) -> DashboardSnapshot:
    as_of = as_of.astimezone(timezone.utc)
    start_dt = datetime.combine(as_of.date(), datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(as_of.date(), datetime.max.time(), tzinfo=timezone.utc)
    month_start_dt = datetime(as_of.year, as_of.month, 1, tzinfo=timezone.utc)
    year_start_dt = datetime(as_of.year, 1, 1, tzinfo=timezone.utc)

    if start_date:
        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    if end_date:
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

    finance = FinanceSnapshot(currency=currency)

    finance.open_invoices = int(
        session.execute(
            select(sa.func.count(Invoice.id)).where(
                Invoice.status.in_(["draft", "submitted", "approved", "partially_paid"])
            )
        ).scalar_one()
        or 0
    )
    finance.pending_approvals = int(
        session.execute(select(sa.func.count(Invoice.id)).where(Invoice.status == "submitted")).scalar_one()
        or 0
    )

    finance.collected_today = _money(
        session.execute(
            select(sa.func.coalesce(sa.func.sum(Payment.amount), 0)).where(
                Payment.status != "voided",
                Payment.paid_at.is_not(None),
                Payment.currency == currency,
                Payment.paid_at >= datetime.combine(as_of.date(), datetime.min.time(), tzinfo=timezone.utc),
                Payment.paid_at <= datetime.combine(as_of.date(), datetime.max.time(), tzinfo=timezone.utc),
            )
        ).scalar_one()
    )

    finance.collected_mtd = _money(
        session.execute(
            select(sa.func.coalesce(sa.func.sum(Payment.amount), 0)).where(
                Payment.status != "voided",
                Payment.paid_at.is_not(None),
                Payment.currency == currency,
                Payment.paid_at >= month_start_dt,
                Payment.paid_at <= end_dt,
            )
        ).scalar_one()
    )

    finance.collected_ytd = _money(
        session.execute(
            select(sa.func.coalesce(sa.func.sum(Payment.amount), 0)).where(
                Payment.status != "voided",
                Payment.paid_at.is_not(None),
                Payment.currency == currency,
                Payment.paid_at >= year_start_dt,
                Payment.paid_at <= end_dt,
            )
        ).scalar_one()
    )

    paid_subq = _paid_totals_subquery()
    finance.outstanding = _money(
        session.execute(
            select(
                sa.func.coalesce(
                    sa.func.sum(Invoice.total - sa.func.coalesce(paid_subq.c.paid_total, 0)),
                    0,
                )
            )
            .outerjoin(paid_subq, paid_subq.c.invoice_id == Invoice.id)
            .where(
                Invoice.status.in_(["approved", "partially_paid"]),
                Invoice.currency == currency,
                ~Invoice.id.in_(expired_hold_invoice_ids_query()),
            )
        ).scalar_one()
    )

    finance.receipts_issued_today = int(
        session.execute(
            select(sa.func.count(Receipt.id))
            .join(Payment, Payment.id == Receipt.payment_id)
            .where(
                Payment.status != "voided",
                Receipt.issued_at.is_not(None),
                Receipt.issued_at
                >= datetime.combine(as_of.date(), datetime.min.time(), tzinfo=timezone.utc),
                Receipt.issued_at
                <= datetime.combine(as_of.date(), datetime.max.time(), tzinfo=timezone.utc),
            )
        ).scalar_one()
        or 0
    )

    active_reserved_bed_query = (
        select(sa.distinct(BedReservation.bed_id))
        .join(Bed, Bed.id == BedReservation.bed_id)
        .join(Room, Room.id == Bed.room_id)
        .outerjoin(Invoice, Invoice.id == BedReservation.invoice_id)
        .where(
            BedReservation.status == "ACTIVE",
            sa.or_(
                BedReservation.invoice_id.is_(None),
                Invoice.status.in_(UNPAID_INVOICE_STATUSES),
            ),
        )
    )
    if block_id is not None:
        active_reserved_bed_query = active_reserved_bed_query.where(Room.block_id == block_id)
    if floor_id is not None:
        active_reserved_bed_query = active_reserved_bed_query.where(Room.floor_id == floor_id)
    reserved_bed_ids = set(session.execute(active_reserved_bed_query).scalars().all())

    if include_occupancy_tables:
        bed_rows_query = (
            select(
                Bed.id,
                Bed.status,
                Block.name.label("block_name"),
                sa.func.coalesce(Floor.floor_label, "").label("floor_label"),
            )
            .join(Room, Room.id == Bed.room_id)
            .join(Block, Block.id == Room.block_id)
            .outerjoin(Floor, Floor.id == Room.floor_id)
        )
    else:
        bed_rows_query = select(Bed.id, Bed.status).join(Room, Room.id == Bed.room_id)
    if block_id is not None:
        bed_rows_query = bed_rows_query.where(Room.block_id == block_id)
    if floor_id is not None:
        bed_rows_query = bed_rows_query.where(Room.floor_id == floor_id)
    bed_rows = session.execute(bed_rows_query).all()

    bed_counts = {"AVAILABLE": 0, "OCCUPIED": 0, "OUT_OF_SERVICE": 0}
    reserved_total = 0
    block_totals: dict[str, dict[str, int]] = {}
    floor_totals: dict[tuple[str, str], dict[str, int]] = {}
    for row in bed_rows:
        if include_occupancy_tables:
            bed_id, status, block_name, floor_label = row
        else:
            bed_id, status = row
            block_name = ""
            floor_label = ""
        status_text = str(status)
        is_reserved = bed_id in reserved_bed_ids or status_text == "RESERVED"
        if is_reserved:
            reserved_total += 1

        block_bucket: dict[str, int] | None = None
        floor_bucket: dict[str, int] | None = None
        if include_occupancy_tables:
            block_bucket = block_totals.setdefault(
                block_name,
                {"total": 0, "occupied": 0, "reserved": 0, "available": 0, "out_of_service": 0},
            )
            floor_key = (block_name, floor_label)
            floor_bucket = floor_totals.setdefault(
                floor_key,
                {"total": 0, "occupied": 0, "reserved": 0, "available": 0, "out_of_service": 0},
            )
            block_bucket["total"] += 1
            floor_bucket["total"] += 1
            if is_reserved:
                block_bucket["reserved"] += 1
                floor_bucket["reserved"] += 1

        if status_text == "OCCUPIED":
            bed_counts["OCCUPIED"] += 1
            if block_bucket is not None and floor_bucket is not None:
                block_bucket["occupied"] += 1
                floor_bucket["occupied"] += 1
        elif status_text == "OUT_OF_SERVICE":
            bed_counts["OUT_OF_SERVICE"] += 1
            if block_bucket is not None and floor_bucket is not None:
                block_bucket["out_of_service"] += 1
                floor_bucket["out_of_service"] += 1
        elif status_text == "AVAILABLE":
            bed_counts["AVAILABLE"] += 1
            if block_bucket is not None and floor_bucket is not None:
                block_bucket["available"] += 1
                floor_bucket["available"] += 1

    occupancy = OccupancySnapshot(
        total_beds=len(bed_rows),
        available_beds=bed_counts["AVAILABLE"],
        reserved_beds=reserved_total,
        occupied_beds=bed_counts["OCCUPIED"],
        out_of_service_beds=bed_counts["OUT_OF_SERVICE"],
    )

    block_occupancy_rows: list[dict[str, Any]] = []
    floor_occupancy_rows: list[dict[str, Any]] = []
    if include_occupancy_tables:
        for block_name in sorted(block_totals.keys()):
            row = block_totals[block_name]
            total = row["total"]
            operational = max(total - row["out_of_service"], 0)
            occupancy_rate = (row["occupied"] / operational) if operational else 0
            block_occupancy_rows.append(
                {
                    "Block": block_name,
                    "Total": total,
                    "Occupied": row["occupied"],
                    "Reserved": row["reserved"],
                    "Available": row["available"],
                    "Out of service": row["out_of_service"],
                    "Occupancy %": f"{occupancy_rate:.0%}",
                }
            )

        for (block_name, floor_label), row in sorted(floor_totals.items(), key=lambda item: (item[0][0], item[0][1])):
            total = row["total"]
            operational = max(total - row["out_of_service"], 0)
            occupancy_rate = (row["occupied"] / operational) if operational else 0
            floor_occupancy_rows.append(
                {
                    "Block": block_name,
                    "Floor": floor_label or "Unassigned",
                    "Total": total,
                    "Occupied": row["occupied"],
                    "Reserved": row["reserved"],
                    "Available": row["available"],
                    "Out of service": row["out_of_service"],
                    "Occupancy %": f"{occupancy_rate:.0%}",
                }
            )

    room_rows_query = (
        select(
            Block.name.label("block_name"),
            Room.room_code.label("room_code"),
            Room.unit_price_per_bed.label("price"),
            sa.func.count(Bed.id).label("total_beds"),
            sa.func.coalesce(sa.func.sum(sa.case((Bed.status == "AVAILABLE", 1), else_=0)), 0).label(
                "available_beds"
            ),
        )
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Bed, Bed.room_id == Room.id)
    )
    if block_id is not None:
        room_rows_query = room_rows_query.where(Room.block_id == block_id)
    if floor_id is not None:
        room_rows_query = room_rows_query.where(Room.floor_id == floor_id)

    room_rows = session.execute(
        room_rows_query
        .group_by(Block.name, Room.room_code, Room.unit_price_per_bed)
        .order_by(
            sa.func.coalesce(sa.func.sum(sa.case((Bed.status == "AVAILABLE", 1), else_=0)), 0).asc(),
            Room.room_code.asc(),
        )
        .limit(8)
    ).all()

    room_availability_rows: list[dict[str, Any]] = []
    for block_name, room_code, price, total_beds, available_beds in room_rows:
        room_availability_rows.append(
            {
                "Block": block_name,
                "Room": room_code,
                "Available/Total": f"{int(available_beds)}/{int(total_beds)}",
                "Price": str(price),
            }
        )

    active_reservations_rows = session.execute(
        select(
            BedReservation.bed_id,
            BedReservation.expires_at,
            Invoice.invoice_no,
            Tenant.name,
        )
        .join(Bed, Bed.id == BedReservation.bed_id)
        .join(Room, Room.id == Bed.room_id)
        .join(Tenant, Tenant.id == BedReservation.tenant_id)
        .outerjoin(Invoice, Invoice.id == BedReservation.invoice_id)
        .where(
            BedReservation.status == "ACTIVE",
            sa.or_(
                BedReservation.invoice_id.is_(None),
                Invoice.status.in_(UNPAID_INVOICE_STATUSES),
            ),
        )
    ).all()
    reservation_map: dict[int, tuple[str, str, str]] = {}
    for bed_id, expires_at, invoice_no, tenant_name in active_reservations_rows:
        reservation_map[int(bed_id)] = (
            expires_at.isoformat() if expires_at else "",
            invoice_no or "",
            tenant_name or "",
        )

    bed_details_query = (
        select(
            Bed.id,
            Bed.bed_label,
            Bed.bed_number,
            Bed.status,
            Room.room_code,
            Room.unit_price_per_bed,
            sa.func.coalesce(Floor.floor_label, "Unassigned"),
            Block.name,
        )
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
    )
    if block_id is not None:
        bed_details_query = bed_details_query.where(Room.block_id == block_id)
    if floor_id is not None:
        bed_details_query = bed_details_query.where(Room.floor_id == floor_id)
    bed_details_rows = session.execute(
        bed_details_query.order_by(
            Block.name.asc(),
            sa.func.coalesce(Floor.floor_label, "Unassigned").asc(),
            Room.room_code.asc(),
            Bed.bed_number.asc(),
        )
    ).all()

    bed_availability_rows: list[dict[str, Any]] = []
    for bed_id, bed_label, _bed_number, bed_status, room_code, unit_price, floor_label, block_name in bed_details_rows:
        reservation_expires, reservation_invoice, reservation_tenant = reservation_map.get(int(bed_id), ("", "", ""))
        status = "RESERVED" if int(bed_id) in reserved_bed_ids else str(bed_status)
        bed_availability_rows.append(
            {
                "Block": block_name,
                "Floor": floor_label or "Unassigned",
                "Room": room_code,
                "Bed": bed_label,
                "Status": status,
                "Price/bed": str(unit_price),
                "Reservation Expires": reservation_expires,
                "Invoice": reservation_invoice,
                "Tenant": reservation_tenant,
            }
        )

    expiring_cutoff = as_of + timedelta(hours=24)
    expiring_filter = (
        BedReservation.status == "ACTIVE",
        BedReservation.expires_at.is_not(None),
        BedReservation.expires_at >= as_of,
        BedReservation.expires_at <= expiring_cutoff,
        sa.or_(
            BedReservation.invoice_id.is_(None),
            Invoice.status.in_(UNPAID_INVOICE_STATUSES),
        ),
    )
    expiring_query = (
        select(BedReservation, Bed, Room, Block, Tenant, Invoice)
        .join(Bed, Bed.id == BedReservation.bed_id)
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .join(Tenant, Tenant.id == BedReservation.tenant_id)
        .outerjoin(Invoice, Invoice.id == BedReservation.invoice_id)
        .where(*expiring_filter)
    )
    if block_id is not None:
        expiring_query = expiring_query.where(Room.block_id == block_id)
    if floor_id is not None:
        expiring_query = expiring_query.where(Room.floor_id == floor_id)

    expiring_count = int(
        session.execute(select(sa.func.count()).select_from(expiring_query.subquery())).scalar_one() or 0
    )
    expiring_rows_raw = session.execute(expiring_query.order_by(BedReservation.expires_at.asc()).limit(5)).all()

    expiring_rows: list[dict[str, Any]] = []
    for reservation, bed, room, block, tenant, invoice in expiring_rows_raw:
        expiring_rows.append(
            {
                "Reservation": reservation.id,
                "Tenant": tenant.name,
                "Room": f"{block.name} {room.room_code}",
                "Bed": bed.bed_label,
                "Invoice": invoice.invoice_no if invoice else "",
                "Expires": reservation.expires_at.isoformat() if reservation.expires_at else "",
            }
        )

    onboarding = get_onboarding_pipeline(
        session,
        as_of=as_of,
        block_id=block_id,
        floor_id=floor_id,
    )
    alerts = AlertSnapshot(
        expiring_reservations_count=expiring_count,
        approved_unpaid_count=onboarding.prospects_with_approved_unpaid,
        paid_unallocated_count=onboarding.paid_unallocated_tenants,
        expiring_reservations_rows=expiring_rows,
    )

    return DashboardSnapshot(
        as_of=as_of,
        currency=currency,
        occupancy=occupancy,
        finance=finance,
        onboarding=onboarding,
        alerts=alerts,
        room_availability_rows=room_availability_rows,
        bed_availability_rows=bed_availability_rows,
        block_occupancy_rows=block_occupancy_rows,
        floor_occupancy_rows=floor_occupancy_rows,
    )
