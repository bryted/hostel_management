from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bed, Block, Floor, Room
from app.services.common import format_money, get_base_currency
from app.services.inventory import (
    apply_inventory_rows,
    create_room_with_beds,
    parse_inventory_upload,
    parse_inventory_upload_file,
    room_bed_integrity_rows,
    update_room_with_effects,
)
from ...deps import get_db_session, require_admin
from ...schemas import (
    ActionResponse,
    BlockOption,
    CreateBlockRequest,
    CreateFloorRequest,
    FloorOption,
    InventoryOverviewResponse,
    InventoryRoomItem,
    RoomPayload,
    UpdateBlockRequest,
    UpdateFloorRequest,
)

router = APIRouter()


@router.get("/overview", response_model=InventoryOverviewResponse)
def get_inventory_overview(
    _user: dict = Depends(require_admin),
    session: Session = Depends(get_db_session),
) -> InventoryOverviewResponse:
    currency = get_base_currency()
    blocks = session.execute(select(Block).order_by(Block.name.asc())).scalars().all()
    floors = session.execute(
        select(Floor, Block).join(Block, Block.id == Floor.block_id).order_by(Block.name.asc(), Floor.floor_label.asc())
    ).all()
    rooms = session.execute(
        select(Room, Floor, Block)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .order_by(Block.name.asc(), Floor.floor_label.asc(), Room.room_code.asc())
    ).all()
    beds = session.execute(select(Bed).order_by(Bed.room_id.asc(), Bed.bed_number.asc())).scalars().all()

    bed_counts: dict[int, dict[str, int]] = {}
    for bed in beds:
        counts = bed_counts.setdefault(int(bed.room_id), {"AVAILABLE": 0, "RESERVED": 0, "OCCUPIED": 0, "OUT_OF_SERVICE": 0})
        counts[bed.status] = counts.get(bed.status, 0) + 1

    return InventoryOverviewResponse(
        total_blocks=len(blocks),
        total_floors=len(floors),
        total_rooms=len(rooms),
        total_beds=len(beds),
        blocks=[BlockOption(id=int(block.id), name=block.name, is_active=bool(block.is_active)) for block in blocks],
        floors=[
            FloorOption(
                id=int(floor.id),
                block_id=int(block.id),
                block_name=block.name,
                floor_label=floor.floor_label,
                is_active=bool(floor.is_active),
            )
            for floor, block in floors
        ],
        rooms=[
            InventoryRoomItem(
                room_id=int(room.id),
                block_id=int(block.id),
                block_name=block.name,
                floor_id=int(floor.id) if floor is not None else None,
                floor_label=floor.floor_label if floor is not None else None,
                room_code=room.room_code,
                room_type=room.room_type,
                beds_count=int(room.beds_count),
                available_beds=bed_counts.get(int(room.id), {}).get("AVAILABLE", 0),
                reserved_beds=bed_counts.get(int(room.id), {}).get("RESERVED", 0),
                occupied_beds=bed_counts.get(int(room.id), {}).get("OCCUPIED", 0),
                out_of_service_beds=bed_counts.get(int(room.id), {}).get("OUT_OF_SERVICE", 0),
                unit_price_per_bed=format_money(room.unit_price_per_bed, currency),
                is_active=bool(room.is_active),
            )
            for room, floor, block in rooms
        ],
        integrity_rows=room_bed_integrity_rows(session),
    )


@router.post("/blocks", response_model=ActionResponse)
def create_block_route(
    payload: CreateBlockRequest,
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> ActionResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Block name is required.")
    existing = session.execute(select(Block).where(Block.name == name)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Block already exists.")
    block = Block(name=name, is_active=True)
    session.add(block)
    session.commit()
    return ActionResponse(message="Block created.")


@router.post("/blocks/{block_id}", response_model=ActionResponse)
def update_block_route(
    block_id: int,
    payload: UpdateBlockRequest,
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> ActionResponse:
    block = session.get(Block, block_id)
    if block is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found.")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Block name is required.")
    if not payload.is_active:
        active_rooms = session.execute(
            select(Room.id).where(Room.block_id == block.id, Room.is_active.is_(True)).limit(1)
        ).scalar_one_or_none()
        if active_rooms is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deactivate rooms in this block before disabling it.")
    block.name = name
    block.is_active = payload.is_active
    session.commit()
    return ActionResponse(message="Block updated.")


@router.post("/floors", response_model=ActionResponse)
def create_floor_route(
    payload: CreateFloorRequest,
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> ActionResponse:
    block = session.get(Block, payload.block_id)
    if block is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found.")
    label = payload.floor_label.strip()
    if not label:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Floor label is required.")
    existing = session.execute(
        select(Floor).where(Floor.block_id == block.id, Floor.floor_label == label)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Floor already exists in this block.")
    floor = Floor(block_id=int(block.id), floor_label=label, is_active=True)
    session.add(floor)
    session.commit()
    return ActionResponse(message="Floor created.")


@router.post("/floors/{floor_id}", response_model=ActionResponse)
def update_floor_route(
    floor_id: int,
    payload: UpdateFloorRequest,
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> ActionResponse:
    floor = session.get(Floor, floor_id)
    if floor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found.")
    label = payload.floor_label.strip()
    if not label:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Floor label is required.")
    if not payload.is_active:
        active_rooms = session.execute(
            select(Room.id).where(Room.floor_id == floor.id, Room.is_active.is_(True)).limit(1)
        ).scalar_one_or_none()
        if active_rooms is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deactivate rooms on this floor before disabling it.")
    floor.floor_label = label
    floor.is_active = payload.is_active
    session.commit()
    return ActionResponse(message="Floor updated.")


@router.post("/rooms", response_model=ActionResponse)
def create_room_route(
    payload: RoomPayload,
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    try:
        room = create_room_with_beds(session, payload.model_dump(), int(user["id"]))
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ActionResponse(message=f"Room {room.room_code} created.")


@router.post("/rooms/{room_id}", response_model=ActionResponse)
def update_room_route(
    room_id: int,
    payload: RoomPayload,
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    try:
        result = update_room_with_effects(
            session,
            room_id,
            payload.model_dump(),
            int(user["id"]),
            datetime.now(timezone.utc),
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    message = f"Room updated."
    if result.repriced_invoices:
        message = f"Room updated. Repriced invoices: {result.repriced_invoices}."
    return ActionResponse(message=message)


@router.post("/upload", response_model=ActionResponse)
async def upload_inventory_route(
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    file_bytes = await file.read()
    df, err = parse_inventory_upload_file(file.filename or "", file_bytes)
    if err or df is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err or "Upload failed.")
    rows, errors = parse_inventory_upload(df)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=" | ".join(errors[:10]),
        )
    try:
        result = apply_inventory_rows(session, rows, int(user["id"]), mode="upsert")
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ActionResponse(
        message=(
            f"Inventory upload applied. Created rooms: {result.created_rooms}. "
            f"Updated rooms: {result.updated_rooms}."
        )
    )
