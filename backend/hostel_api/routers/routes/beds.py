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
from ...schemas import ActionResponse, BedListItem, SetMaintenanceRequest

router = APIRouter()


@router.get("", response_model=list[BedListItem])
def list_beds(
    block_id: int | None = Query(default=None),
    floor_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> list[BedListItem]:
    currency = get_base_currency()
    bed_rows = session.execute(
        select(Bed, Room, Floor, Block)
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .order_by(Block.name.asc(), Floor.floor_label.asc(), Room.room_code.asc(), Bed.bed_number.asc())
    ).all()
    reservation_rows = session.execute(
        select(BedReservation, Tenant, Invoice)
        .join(Tenant, Tenant.id == BedReservation.tenant_id)
        .outerjoin(Invoice, Invoice.id == BedReservation.invoice_id)
        .where(BedReservation.status == "ACTIVE")
    ).all()
    allocation_rows = session.execute(
        select(Allocation, Tenant, Invoice)
        .join(Tenant, Tenant.id == Allocation.tenant_id)
        .outerjoin(Invoice, Invoice.id == Allocation.invoice_id)
        .where(Allocation.status == "CONFIRMED")
    ).all()
    reservation_by_bed = {int(reservation.bed_id): (reservation, tenant, invoice) for reservation, tenant, invoice in reservation_rows}
    allocation_by_bed = {int(allocation.bed_id): (allocation, tenant, invoice) for allocation, tenant, invoice in allocation_rows}
    results: list[BedListItem] = []
    for bed, room, floor, block in bed_rows:
        if block_id is not None and int(block.id) != int(block_id):
            continue
        if floor_id is not None and (floor is None or int(floor.id) != int(floor_id)):
            continue
        if status_filter and bed.status != status_filter:
            continue
        reservation = reservation_by_bed.get(int(bed.id))
        allocation = allocation_by_bed.get(int(bed.id))
        tenant = allocation[1] if allocation else (reservation[1] if reservation else None)
        invoice = allocation[2] if allocation and allocation[2] else (reservation[2] if reservation and reservation[2] else None)
        floor_label = floor.floor_label if floor else "Unassigned"
        haystack = " ".join(
            [
                block.name,
                floor_label,
                room.room_code,
                bed.bed_label,
                bed.status,
                tenant.name if tenant else "",
                invoice.invoice_no if invoice else "",
            ]
        ).lower()
        if search and search.strip() and search.strip().lower() not in haystack:
            continue
        results.append(
            BedListItem(
                bed_id=int(bed.id),
                block=block.name,
                floor=floor_label,
                room=room.room_code,
                bed=bed.bed_label,
                status=bed.status,
                tenant=tenant.name if tenant else None,
                tenant_id=int(tenant.id) if tenant else None,
                invoice=invoice.invoice_no if invoice else None,
                invoice_id=int(invoice.id) if invoice else None,
                reservation_id=int(reservation[0].id) if reservation else None,
                allocation_id=int(allocation[0].id) if allocation else None,
                price_per_bed=format_money(room.unit_price_per_bed, currency),
                reservation_expires=reservation[0].expires_at.isoformat() if reservation and reservation[0].expires_at else None,
                allocation_start=allocation[0].start_date.isoformat() if allocation and allocation[0].start_date else None,
            )
        )
        if len(results) >= limit:
            break
    return results


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
