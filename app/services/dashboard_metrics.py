from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, Bed, BedReservation, Block, Floor, Invoice, Payment, Receipt, Room, Tenant
from app.services.invoicing import paid_totals_subquery
from app.services.onboarding import get_onboarding_pipeline
from app.services.reservations import expired_hold_invoice_ids_query
from app.services.types import (
    AlertSnapshot,
    DashboardSnapshot,
    FinanceSnapshot,
    OccupancySnapshot,
    OnboardingPipelineSnapshot,
)

UNPAID_INVOICE_STATUSES = ("draft", "submitted", "approved", "partially_paid")


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _reserved_beds_subquery(block_id: int | None, floor_id: int | None) -> sa.Subquery:
    query = (
        select(BedReservation.bed_id.label("bed_id"))
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
        .group_by(BedReservation.bed_id)
    )
    if block_id is not None:
        query = query.where(Room.block_id == block_id)
    if floor_id is not None:
        query = query.where(Room.floor_id == floor_id)
    return query.subquery()


def _occupancy_aggregates(
    session: Session,
    *,
    block_id: int | None,
    floor_id: int | None,
    include_tables: bool,
) -> tuple[OccupancySnapshot, list[dict[str, Any]], list[dict[str, Any]], set[int]]:
    reserved_beds = _reserved_beds_subquery(block_id, floor_id)
    is_reserved_expr = sa.or_(Bed.status == "RESERVED", reserved_beds.c.bed_id.is_not(None))
    floor_label_expr = sa.func.coalesce(Floor.floor_label, "Unassigned")

    base_query = (
        select(
            Bed.id.label("bed_id"),
            Bed.status.label("bed_status"),
            Block.name.label("block_name"),
            floor_label_expr.label("floor_label"),
            sa.case((is_reserved_expr, 1), else_=0).label("reserved_flag"),
            sa.case((Bed.status == "AVAILABLE", 1), else_=0).label("available_flag"),
            sa.case((Bed.status == "OCCUPIED", 1), else_=0).label("occupied_flag"),
            sa.case((Bed.status == "OUT_OF_SERVICE", 1), else_=0).label("out_of_service_flag"),
        )
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .outerjoin(reserved_beds, reserved_beds.c.bed_id == Bed.id)
    )
    if block_id is not None:
        base_query = base_query.where(Room.block_id == block_id)
    if floor_id is not None:
        base_query = base_query.where(Room.floor_id == floor_id)
    bed_state = base_query.subquery()

    summary_row = session.execute(
        select(
            sa.func.count(bed_state.c.bed_id),
            sa.func.coalesce(sa.func.sum(bed_state.c.available_flag), 0),
            sa.func.coalesce(sa.func.sum(bed_state.c.reserved_flag), 0),
            sa.func.coalesce(sa.func.sum(bed_state.c.occupied_flag), 0),
            sa.func.coalesce(sa.func.sum(bed_state.c.out_of_service_flag), 0),
        )
    ).one()

    occupancy = OccupancySnapshot(
        total_beds=int(summary_row[0] or 0),
        available_beds=int(summary_row[1] or 0),
        reserved_beds=int(summary_row[2] or 0),
        occupied_beds=int(summary_row[3] or 0),
        out_of_service_beds=int(summary_row[4] or 0),
    )

    reserved_bed_ids = set(
        int(bed_id)
        for bed_id in session.execute(select(reserved_beds.c.bed_id)).scalars().all()
        if bed_id is not None
    )

    if not include_tables:
        return occupancy, [], [], reserved_bed_ids

    block_rows = session.execute(
        select(
            bed_state.c.block_name,
            sa.func.count(bed_state.c.bed_id),
            sa.func.coalesce(sa.func.sum(bed_state.c.occupied_flag), 0),
            sa.func.coalesce(sa.func.sum(bed_state.c.reserved_flag), 0),
            sa.func.coalesce(sa.func.sum(bed_state.c.available_flag), 0),
            sa.func.coalesce(sa.func.sum(bed_state.c.out_of_service_flag), 0),
        )
        .group_by(bed_state.c.block_name)
        .order_by(bed_state.c.block_name.asc())
    ).all()
    block_occupancy_rows: list[dict[str, Any]] = []
    for block_name, total, occupied, reserved, available, out_of_service in block_rows:
        operational = max(int(total or 0) - int(out_of_service or 0), 0)
        occupancy_rate = (int(occupied or 0) / operational) if operational else 0
        block_occupancy_rows.append(
            {
                "Block": block_name,
                "Total": int(total or 0),
                "Occupied": int(occupied or 0),
                "Reserved": int(reserved or 0),
                "Available": int(available or 0),
                "Out of service": int(out_of_service or 0),
                "Occupancy %": f"{occupancy_rate:.0%}",
            }
        )

    floor_rows = session.execute(
        select(
            bed_state.c.block_name,
            bed_state.c.floor_label,
            sa.func.count(bed_state.c.bed_id),
            sa.func.coalesce(sa.func.sum(bed_state.c.occupied_flag), 0),
            sa.func.coalesce(sa.func.sum(bed_state.c.reserved_flag), 0),
            sa.func.coalesce(sa.func.sum(bed_state.c.available_flag), 0),
            sa.func.coalesce(sa.func.sum(bed_state.c.out_of_service_flag), 0),
        )
        .group_by(bed_state.c.block_name, bed_state.c.floor_label)
        .order_by(bed_state.c.block_name.asc(), bed_state.c.floor_label.asc())
    ).all()
    floor_occupancy_rows: list[dict[str, Any]] = []
    for block_name, floor_label, total, occupied, reserved, available, out_of_service in floor_rows:
        operational = max(int(total or 0) - int(out_of_service or 0), 0)
        occupancy_rate = (int(occupied or 0) / operational) if operational else 0
        floor_occupancy_rows.append(
            {
                "Block": block_name,
                "Floor": floor_label or "Unassigned",
                "Total": int(total or 0),
                "Occupied": int(occupied or 0),
                "Reserved": int(reserved or 0),
                "Available": int(available or 0),
                "Out of service": int(out_of_service or 0),
                "Occupancy %": f"{occupancy_rate:.0%}",
            }
        )

    return occupancy, block_occupancy_rows, floor_occupancy_rows, reserved_bed_ids


def get_dashboard_snapshot(
    session: Session,
    as_of: datetime,
    currency: str = "GHS",
    start_date: date | None = None,
    end_date: date | None = None,
    block_id: int | None = None,
    floor_id: int | None = None,
    include_occupancy_tables: bool = True,
    include_availability_rows: bool = True,
    include_onboarding: bool = True,
    include_alert_rows: bool = True,
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
        session.execute(select(sa.func.count(Invoice.id)).where(Invoice.status == "submitted")).scalar_one() or 0
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

    paid_subq = paid_totals_subquery()
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
                Receipt.issued_at >= datetime.combine(as_of.date(), datetime.min.time(), tzinfo=timezone.utc),
                Receipt.issued_at <= datetime.combine(as_of.date(), datetime.max.time(), tzinfo=timezone.utc),
            )
        ).scalar_one()
        or 0
    )

    occupancy, block_occupancy_rows, floor_occupancy_rows, reserved_bed_ids = _occupancy_aggregates(
        session,
        block_id=block_id,
        floor_id=floor_id,
        include_tables=include_occupancy_tables,
    )

    room_availability_rows: list[dict[str, Any]] = []
    bed_availability_rows: list[dict[str, Any]] = []
    if include_availability_rows:
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
        room_availability_rows = [
            {
                "Block": block_name,
                "Room": room_code,
                "Available/Total": f"{int(available_beds)}/{int(total_beds)}",
                "Price": str(price),
            }
            for block_name, room_code, price, total_beds, available_beds in room_rows
        ]

        active_reservations_query = (
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
        )
        if block_id is not None:
            active_reservations_query = active_reservations_query.where(Room.block_id == block_id)
        if floor_id is not None:
            active_reservations_query = active_reservations_query.where(Room.floor_id == floor_id)

        reservation_map: dict[int, tuple[str, str, str]] = {}
        for bed_id, expires_at, invoice_no, tenant_name in session.execute(active_reservations_query).all():
            reservation_map[int(bed_id)] = (
                expires_at.isoformat() if expires_at else "",
                invoice_no or "",
                tenant_name or "",
            )

        bed_details_query = (
            select(
                Bed.id,
                Bed.bed_label,
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
        for bed_id, bed_label, bed_status, room_code, unit_price, floor_label, block_name in bed_details_rows:
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

    onboarding = (
        get_onboarding_pipeline(
            session,
            as_of=as_of,
            block_id=block_id,
            floor_id=floor_id,
        )
        if include_onboarding or include_alert_rows
        else OnboardingPipelineSnapshot()
    )

    alerts = AlertSnapshot()
    if include_alert_rows:
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
        expiring_rows: list[dict[str, Any]] = []
        for reservation, bed, room, block, tenant, invoice in session.execute(
            expiring_query.order_by(BedReservation.expires_at.asc()).limit(5)
        ).all():
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
