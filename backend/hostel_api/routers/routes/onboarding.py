from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models import Bed, Block, Floor, Room
from app.services.common import format_money, get_base_currency
from app.services.onboarding import get_onboarding_pipeline, get_onboarding_queue
from ...deps import get_db_session, require_admin
from ...schemas import BedOption, OnboardingOverviewResponse, OnboardingQueueItem

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


@router.get("/queue", response_model=OnboardingOverviewResponse)
def get_onboarding_overview(
    search: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _user: dict = Depends(require_admin),
    session: Session = Depends(get_db_session),
) -> OnboardingOverviewResponse:
    currency = get_base_currency()
    snapshot = get_onboarding_pipeline(
        session,
        as_of=datetime.now(timezone.utc),
    )
    rows = get_onboarding_queue(session, limit=200)

    if stage and stage.strip():
        normalized_stage = stage.strip().lower()
        rows = [row for row in rows if str(row.get("Stage", "")).lower() == normalized_stage]

    if search and search.strip():
        needle = search.strip().lower()
        rows = [
            row
            for row in rows
            if needle in " ".join(
                [
                    str(row.get("Tenant", "")),
                    str(row.get("Invoice", "")),
                    str(row.get("Invoice status", "")),
                    str(row.get("Stage", "")),
                ]
            ).lower()
        ]

    reserved_bed_ids = {
        int(row["Reserved bed ID"])
        for row in rows
        if row.get("Reserved bed ID") is not None
    }
    reserved_bed_rows = (
        session.execute(
            select(Bed, Room, Floor, Block)
            .join(Room, Room.id == Bed.room_id)
            .join(Block, Block.id == Room.block_id)
            .outerjoin(Floor, Floor.id == Room.floor_id)
            .where(Bed.id.in_(reserved_bed_ids))
        ).all()
        if reserved_bed_ids
        else []
    )
    reserved_bed_labels = {
        int(bed.id): _bed_option(bed, room, floor, block).label
        for bed, room, floor, block in reserved_bed_rows
    }

    queue_items = [
        OnboardingQueueItem(
            stage=str(row["Stage"]),
            tenant_id=int(row["Tenant ID"]),
            tenant_name=str(row["Tenant"]),
            invoice_id=int(row["Invoice ID"]),
            invoice_no=str(row["Invoice"]),
            invoice_status=str(row["Invoice status"]),
            total=format_money(Decimal(str(row["Total"])), currency),
            paid=format_money(Decimal(str(row["Paid"])), currency),
            balance=format_money(Decimal(str(row["Total"])) - Decimal(str(row["Paid"])), currency),
            reserved_bed_id=int(row["Reserved bed ID"]) if row.get("Reserved bed ID") is not None else None,
            reserved_bed_label=reserved_bed_labels.get(int(row["Reserved bed ID"])) if row.get("Reserved bed ID") is not None else None,
            hold_expired=bool(row.get("Hold expired")),
        )
        for row in rows[:limit]
    ]
    bed_rows = session.execute(
        select(Bed, Room, Floor, Block)
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .where(Bed.status == "AVAILABLE")
        .order_by(Block.name.asc(), Floor.floor_label.asc(), Room.room_code.asc(), Bed.bed_number.asc())
        .limit(100)
    ).all()

    return OnboardingOverviewResponse(
        prospects=snapshot.prospects,
        approved_unpaid=snapshot.prospects_with_approved_unpaid,
        paid_unallocated=snapshot.paid_unallocated_tenants,
        active_allocated=snapshot.active_allocated_tenants,
        newly_activated_last_7d=snapshot.newly_activated_last_7d,
        queue_rows=queue_items,
        available_beds=[_bed_option(bed, room, floor, block) for bed, room, floor, block in bed_rows],
    )
