from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, Bed, BedReservation, Block, Floor, Invoice, Room, Tenant
from app.services.lifecycle import end_allocation_stay, format_timestamp, transfer_allocation_bed
from ...deps import get_db_session, require_admin
from ...schemas import (
    ActionResponse,
    AllocationOverviewResponse,
    AllocationRosterItem,
    BedOption,
    EndAllocationRequest,
    TransferAllocationRequest,
)

router = APIRouter()


def _bed_option(bed: Bed, room: Room, floor: Floor | None, block: Block) -> BedOption:
    floor_label = floor.floor_label if floor else "Unassigned"
    return BedOption(
        bed_id=int(bed.id),
        block=block.name,
        floor=floor_label,
        room=room.room_code,
        bed=bed.bed_label,
        status=bed.status,
        label=f"{block.name} / {floor_label} / {room.room_code} / {bed.bed_label}",
    )


@router.get("/overview", response_model=AllocationOverviewResponse)
def get_allocation_overview(
    search: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> AllocationOverviewResponse:
    query = (
        select(Allocation, Tenant, Invoice, Bed, Room, Floor, Block)
        .join(Tenant, Tenant.id == Allocation.tenant_id)
        .outerjoin(Invoice, Invoice.id == Allocation.invoice_id)
        .join(Bed, Bed.id == Allocation.bed_id)
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .where(Allocation.status == "CONFIRMED")
        .order_by(Allocation.created_at.desc())
    )
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(
            sa.or_(
                Tenant.name.ilike(pattern),
                Invoice.invoice_no.ilike(pattern),
                Block.name.ilike(pattern),
                Room.room_code.ilike(pattern),
                Bed.bed_label.ilike(pattern),
            )
        )

    rows = session.execute(query).all()
    roster_rows: list[AllocationRosterItem] = []
    linked_invoices = 0
    for allocation, tenant, invoice, bed, room, floor, block in rows:
        if invoice is not None:
            linked_invoices += 1
        transfer_rows = session.execute(
            select(Bed, Room, Floor, Block)
            .join(Room, Room.id == Bed.room_id)
            .join(Block, Block.id == Room.block_id)
            .outerjoin(Floor, Floor.id == Room.floor_id)
            .where(Bed.id != allocation.bed_id)
            .where(Bed.status.in_(["AVAILABLE", "RESERVED"]))
            .where(
                ~sa.exists(
                    select(Allocation.id).where(
                        Allocation.bed_id == Bed.id,
                        Allocation.status == "CONFIRMED",
                    )
                )
            )
            .where(
                ~sa.exists(
                    select(BedReservation.id).where(
                        BedReservation.bed_id == Bed.id,
                        BedReservation.status == "ACTIVE",
                        sa.or_(
                            BedReservation.invoice_id.is_(None),
                            BedReservation.invoice_id != allocation.invoice_id,
                        ),
                    )
                )
            )
            .order_by(Block.name.asc(), Floor.floor_label.asc(), Room.room_code.asc(), Bed.bed_number.asc())
            .limit(50)
        ).all()
        roster_rows.append(
            AllocationRosterItem(
                allocation_id=int(allocation.id),
                tenant_id=int(tenant.id),
                tenant_name=tenant.name,
                invoice_id=int(invoice.id) if invoice is not None else None,
                invoice_no=invoice.invoice_no if invoice is not None else None,
                block=block.name,
                floor=floor.floor_label if floor else "Unassigned",
                room=room.room_code,
                bed=bed.bed_label,
                start_date=format_timestamp(allocation.start_date),
                transfer_targets=[
                    _bed_option(target_bed, target_room, target_floor, target_block)
                    for target_bed, target_room, target_floor, target_block in transfer_rows
                ],
            )
        )

    return AllocationOverviewResponse(
        active_allocations=len(roster_rows),
        linked_invoices=linked_invoices,
        rows=roster_rows,
    )


@router.post("/{allocation_id}/end", response_model=ActionResponse)
def end_allocation(
    allocation_id: int,
    payload: EndAllocationRequest,
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    try:
        allocation = end_allocation_stay(
            session,
            allocation_id=allocation_id,
            user_id=int(user["id"]),
            now=datetime.now(timezone.utc),
            reason=payload.reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ActionResponse(
        message="Stay ended successfully.",
        allocation_id=int(allocation.id),
        bed_id=int(allocation.bed_id),
    )


@router.post("/{allocation_id}/transfer", response_model=ActionResponse)
def transfer_allocation(
    allocation_id: int,
    payload: TransferAllocationRequest,
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    try:
        allocation = transfer_allocation_bed(
            session,
            allocation_id=allocation_id,
            new_bed_id=payload.new_bed_id,
            user_id=int(user["id"]),
            now=datetime.now(timezone.utc),
            reason=payload.reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ActionResponse(
        message="Allocation transferred successfully.",
        allocation_id=int(allocation.id),
        bed_id=int(allocation.bed_id),
    )
