from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, Bed, BedReservation, Block, Floor, Invoice, Room, Tenant
from app.services.common import format_money, get_base_currency
from app.services.lifecycle import set_bed_maintenance_status
from ...deps import get_current_user, get_db_session, require_admin
from ...schemas import ActionResponse, BedListItem, BedListResponse, SetMaintenanceRequest

router = APIRouter()


@router.get("", response_model=BedListResponse)
def list_beds(
    block_id: int | None = Query(default=None),
    floor_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    _user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> BedListResponse:
    currency = get_base_currency()
    floor_label_expr = sa.func.coalesce(Floor.floor_label, "Unassigned")
    reservation_rows = (
        select(
            BedReservation.bed_id.label("bed_id"),
            BedReservation.id.label("reservation_id"),
            BedReservation.expires_at.label("reservation_expires"),
            Tenant.id.label("tenant_id"),
            Tenant.name.label("tenant_name"),
            Invoice.id.label("invoice_id"),
            Invoice.invoice_no.label("invoice_no"),
        )
        .join(Tenant, Tenant.id == BedReservation.tenant_id)
        .outerjoin(Invoice, Invoice.id == BedReservation.invoice_id)
        .where(BedReservation.status == "ACTIVE")
        .subquery()
    )
    allocation_rows = (
        select(
            Allocation.bed_id.label("bed_id"),
            Allocation.id.label("allocation_id"),
            Allocation.start_date.label("allocation_start"),
            Tenant.id.label("tenant_id"),
            Tenant.name.label("tenant_name"),
            Invoice.id.label("invoice_id"),
            Invoice.invoice_no.label("invoice_no"),
        )
        .join(Tenant, Tenant.id == Allocation.tenant_id)
        .outerjoin(Invoice, Invoice.id == Allocation.invoice_id)
        .where(Allocation.status == "CONFIRMED")
        .subquery()
    )

    tenant_name_expr = sa.func.coalesce(allocation_rows.c.tenant_name, reservation_rows.c.tenant_name)
    tenant_id_expr = sa.func.coalesce(allocation_rows.c.tenant_id, reservation_rows.c.tenant_id)
    invoice_no_expr = sa.func.coalesce(allocation_rows.c.invoice_no, reservation_rows.c.invoice_no)
    invoice_id_expr = sa.func.coalesce(allocation_rows.c.invoice_id, reservation_rows.c.invoice_id)

    base_query = (
        select(
            Bed.id.label("bed_id"),
            Block.name.label("block_name"),
            floor_label_expr.label("floor_label"),
            Room.room_code.label("room_code"),
            Bed.bed_label.label("bed_label"),
            Bed.status.label("bed_status"),
            tenant_name_expr.label("tenant_name"),
            tenant_id_expr.label("tenant_id"),
            invoice_no_expr.label("invoice_no"),
            invoice_id_expr.label("invoice_id"),
            reservation_rows.c.reservation_id.label("reservation_id"),
            allocation_rows.c.allocation_id.label("allocation_id"),
            reservation_rows.c.reservation_expires.label("reservation_expires"),
            allocation_rows.c.allocation_start.label("allocation_start"),
            Room.unit_price_per_bed.label("unit_price_per_bed"),
        )
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .outerjoin(reservation_rows, reservation_rows.c.bed_id == Bed.id)
        .outerjoin(allocation_rows, allocation_rows.c.bed_id == Bed.id)
    )
    if block_id is not None:
        base_query = base_query.where(Room.block_id == block_id)
    if floor_id is not None:
        base_query = base_query.where(Room.floor_id == floor_id)
    if status_filter:
        base_query = base_query.where(Bed.status == status_filter)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        base_query = base_query.where(
            sa.or_(
                Block.name.ilike(pattern),
                floor_label_expr.ilike(pattern),
                Room.room_code.ilike(pattern),
                Bed.bed_label.ilike(pattern),
                sa.cast(Bed.status, sa.String).ilike(pattern),
                tenant_name_expr.ilike(pattern),
                invoice_no_expr.ilike(pattern),
            )
        )

    filtered_beds = base_query.subquery()
    summary_row = session.execute(
        select(
            sa.func.count().label("total"),
            sa.func.coalesce(sa.func.sum(sa.case((filtered_beds.c.bed_status == "AVAILABLE", 1), else_=0)), 0),
            sa.func.coalesce(sa.func.sum(sa.case((filtered_beds.c.bed_status == "RESERVED", 1), else_=0)), 0),
            sa.func.coalesce(sa.func.sum(sa.case((filtered_beds.c.bed_status == "OCCUPIED", 1), else_=0)), 0),
            sa.func.coalesce(sa.func.sum(sa.case((filtered_beds.c.bed_status == "OUT_OF_SERVICE", 1), else_=0)), 0),
        )
    ).one()
    rows = session.execute(
        select(filtered_beds)
        .order_by(
            filtered_beds.c.block_name.asc(),
            filtered_beds.c.floor_label.asc(),
            filtered_beds.c.room_code.asc(),
            filtered_beds.c.bed_label.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return BedListResponse(
        rows=[
            BedListItem(
                bed_id=int(row.bed_id),
                block=row.block_name,
                floor=row.floor_label,
                room=row.room_code,
                bed=row.bed_label,
                status=row.bed_status,
                tenant=row.tenant_name,
                tenant_id=int(row.tenant_id) if row.tenant_id is not None else None,
                invoice=row.invoice_no,
                invoice_id=int(row.invoice_id) if row.invoice_id is not None else None,
                reservation_id=int(row.reservation_id) if row.reservation_id is not None else None,
                allocation_id=int(row.allocation_id) if row.allocation_id is not None else None,
                price_per_bed=format_money(row.unit_price_per_bed, currency),
                reservation_expires=row.reservation_expires.isoformat() if row.reservation_expires is not None else None,
                allocation_start=row.allocation_start.isoformat() if row.allocation_start is not None else None,
            )
            for row in rows
        ],
        total=int(summary_row[0] or 0),
        page=page,
        page_size=page_size,
        available_total=int(summary_row[1] or 0),
        reserved_total=int(summary_row[2] or 0),
        occupied_total=int(summary_row[3] or 0),
        out_of_service_total=int(summary_row[4] or 0),
    )


@router.post("/{bed_id}/maintenance", response_model=ActionResponse)
def update_bed_maintenance(
    bed_id: int,
    payload: SetMaintenanceRequest,
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    try:
        bed = set_bed_maintenance_status(
            session,
            bed_id=bed_id,
            user_id=int(user["id"]),
            now=datetime.now(timezone.utc),
            out_of_service=payload.out_of_service,
            reason=payload.reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ActionResponse(
        message="Bed maintenance status updated.",
        bed_id=int(bed.id),
    )
