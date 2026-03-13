from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, Bed, BedReservation, Block, Floor, Invoice, Payment, Receipt, Room, Tenant
from app.services.common import format_money, get_base_currency
from app.services.invoicing import get_paid_total
from app.services.lifecycle import _log_tenant_event, format_timestamp, get_tenant_timeline_rows
from ...deps import get_current_user, get_db_session
from ...schemas import (
    ActionResponse,
    AllocationSummary,
    BedOption,
    CreateTenantRequest,
    InvoiceSummary,
    PaymentSummary,
    ReceiptSummary,
    ReservationSummary,
    TenantListItem,
    TenantWorkspaceResponse,
    UpdateTenantRequest,
)

router = APIRouter()

VALID_TENANT_STATUSES = {"prospect", "active", "inactive"}


def _tenant_item(tenant: Tenant) -> TenantListItem:
    return TenantListItem(
        id=int(tenant.id),
        name=tenant.name,
        email=tenant.email,
        phone=tenant.phone,
        status=tenant.status,
        room=tenant.room,
    )


def _build_invoice_summary(
    session: Session,
    invoice: Invoice,
    currency: str,
    allocated_invoice_ids: set[int],
) -> InvoiceSummary:
    paid_total = Decimal(str(get_paid_total(session, invoice.id)))
    total = Decimal(str(invoice.total or 0))
    balance = total - paid_total
    can_allocate = balance <= Decimal("0") and int(invoice.id) not in allocated_invoice_ids and invoice.status not in {"draft", "rejected"}
    return InvoiceSummary(
        id=int(invoice.id),
        invoice_no=invoice.invoice_no,
        status=invoice.status,
        total=format_money(total, currency),
        paid_total=format_money(paid_total, currency),
        balance=format_money(balance, currency),
        issued_at=format_timestamp(invoice.issued_at),
        due_at=format_timestamp(invoice.due_at),
        can_allocate=can_allocate,
    )


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


@router.get("", response_model=list[TenantListItem])
def list_tenants(
    search: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    _user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> list[TenantListItem]:
    query = select(Tenant)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(
            sa.or_(
                Tenant.name.ilike(pattern),
                Tenant.email.ilike(pattern),
                Tenant.phone.ilike(pattern),
            )
        )
    tenants = session.execute(query.order_by(Tenant.name.asc()).limit(limit)).scalars().all()
    return [
        _tenant_item(tenant)
        for tenant in tenants
    ]


@router.post("", response_model=ActionResponse)
def create_tenant(
    payload: CreateTenantRequest,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ActionResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant name is required.")
    status_value = payload.status.strip().lower() or "prospect"
    if status_value not in VALID_TENANT_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant status.")
    existing = session.execute(
        select(Tenant).where(sa.func.lower(Tenant.name) == name.lower())
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant with this name already exists.")

    normalized_phone = (payload.phone or "").strip()
    tenant = Tenant(
        name=name,
        email=(payload.email or "").strip() or None,
        phone=normalized_phone or None,
        normalized_phone=normalized_phone or None,
        room=(payload.room or "").strip() or None,
        status=status_value,
    )
    session.add(tenant)
    session.flush()
    _log_tenant_event(session, int(tenant.id), "TENANT_CREATED", int(user["id"]), {"status": tenant.status})
    session.commit()
    return ActionResponse(message="Tenant created.", tenant_id=int(tenant.id))


@router.post("/{tenant_id}", response_model=ActionResponse)
def update_tenant(
    tenant_id: int,
    payload: UpdateTenantRequest,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ActionResponse:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant name is required.")
    status_value = payload.status.strip().lower() or "prospect"
    if status_value not in VALID_TENANT_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant status.")
    existing = session.execute(
        select(Tenant.id).where(sa.func.lower(Tenant.name) == name.lower(), Tenant.id != tenant.id)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant with this name already exists.")

    phone = (payload.phone or "").strip()
    tenant.name = name
    tenant.email = (payload.email or "").strip() or None
    tenant.phone = phone or None
    tenant.normalized_phone = phone or None
    tenant.room = (payload.room or "").strip() or None
    tenant.status = status_value
    _log_tenant_event(session, int(tenant.id), "TENANT_UPDATED", int(user["id"]), {"status": tenant.status})
    session.commit()
    return ActionResponse(message="Tenant updated.", tenant_id=int(tenant.id))


@router.post("/{tenant_id}/archive", response_model=ActionResponse)
def archive_tenant(
    tenant_id: int,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ActionResponse:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    has_active_allocation = session.execute(
        select(Allocation.id).where(Allocation.tenant_id == tenant.id, Allocation.status == "CONFIRMED")
    ).scalar_one_or_none()
    if has_active_allocation is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End the active stay before archiving this tenant.")
    tenant.status = "inactive"
    _log_tenant_event(session, int(tenant.id), "TENANT_ARCHIVED", int(user["id"]), {})
    session.commit()
    return ActionResponse(message="Tenant archived.", tenant_id=int(tenant.id))


@router.get("/{tenant_id}/workspace", response_model=TenantWorkspaceResponse)
def tenant_workspace(
    tenant_id: int,
    _user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> TenantWorkspaceResponse:
    currency = get_base_currency()
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    invoices = session.execute(
        select(Invoice).where(Invoice.tenant_id == tenant.id).order_by(Invoice.created_at.desc())
    ).scalars().all()
    payments = session.execute(
        select(Payment).where(Payment.tenant_id == tenant.id).order_by(sa.func.coalesce(Payment.paid_at, Payment.created_at).desc())
    ).scalars().all()
    receipts = session.execute(
        select(Receipt).where(Receipt.tenant_id == tenant.id).order_by(sa.func.coalesce(Receipt.issued_at, Receipt.created_at).desc())
    ).scalars().all()
    active_reservation = session.execute(
        select(BedReservation, Bed, Room, Floor, Block, Invoice)
        .join(Bed, Bed.id == BedReservation.bed_id)
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .outerjoin(Invoice, Invoice.id == BedReservation.invoice_id)
        .where(BedReservation.tenant_id == tenant.id, BedReservation.status == "ACTIVE")
        .order_by(BedReservation.expires_at.asc())
    ).first()
    active_allocation = session.execute(
        select(Allocation, Bed, Room, Floor, Block, Invoice)
        .join(Bed, Bed.id == Allocation.bed_id)
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .outerjoin(Invoice, Invoice.id == Allocation.invoice_id)
        .where(Allocation.tenant_id == tenant.id, Allocation.status == "CONFIRMED")
        .order_by(Allocation.start_date.desc())
    ).first()
    confirmed_allocations = session.execute(
        select(Allocation).where(Allocation.tenant_id == tenant.id, Allocation.status == "CONFIRMED")
    ).scalars().all()
    allocated_invoice_ids = {int(item.invoice_id) for item in confirmed_allocations if item.invoice_id is not None}

    invoice_summaries = [_build_invoice_summary(session, invoice, currency, allocated_invoice_ids) for invoice in invoices]
    allocatable_invoices = [invoice for invoice in invoice_summaries if invoice.can_allocate]

    bed_rows = session.execute(
        select(Bed, Room, Floor, Block)
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .where(Bed.status == "AVAILABLE")
        .order_by(Block.name.asc(), Floor.floor_label.asc(), Room.room_code.asc(), Bed.bed_number.asc())
        .limit(40)
    ).all()
    available_beds = [_bed_option(bed, room, floor, block) for bed, room, floor, block in bed_rows]

    payment_summaries = [
        PaymentSummary(
            id=int(payment.id),
            payment_no=payment.payment_no,
            amount=format_money(payment.amount, payment.currency),
            method=payment.method,
            reference=payment.reference,
            status=payment.status,
            paid_at=format_timestamp(payment.paid_at or payment.created_at),
        )
        for payment in payments
    ]
    receipt_summaries = [
        ReceiptSummary(
            id=int(receipt.id),
            receipt_no=receipt.receipt_no,
            amount=format_money(receipt.amount, receipt.currency),
            issued_at=format_timestamp(receipt.issued_at or receipt.created_at),
            printed_count=int(receipt.printed_count or 0),
        )
        for receipt in receipts
    ]

    reservation_summary = None
    if active_reservation:
        reservation, bed, room, floor, block, invoice = active_reservation
        reservation_summary = ReservationSummary(
            id=int(reservation.id),
            bed_id=int(bed.id),
            invoice_id=int(invoice.id) if invoice is not None else None,
            invoice_no=invoice.invoice_no if invoice is not None else None,
            block=block.name,
            floor=floor.floor_label if floor else "Unassigned",
            room=room.room_code,
            bed=bed.bed_label,
            expires_at=format_timestamp(reservation.expires_at),
            extension_count=int(reservation.extension_count or 0),
        )

    allocation_summary = None
    if active_allocation:
        allocation, bed, room, floor, block, invoice = active_allocation
        allocation_summary = AllocationSummary(
            id=int(allocation.id),
            bed_id=int(bed.id),
            invoice_id=int(invoice.id) if invoice is not None else None,
            invoice_no=invoice.invoice_no if invoice is not None else None,
            block=block.name,
            floor=floor.floor_label if floor else "Unassigned",
            room=room.room_code,
            bed=bed.bed_label,
            start_date=format_timestamp(allocation.start_date),
        )

    next_action = "review_billing"
    payable_invoice_exists = any(
        invoice.status not in {"draft", "rejected"}
        and Decimal(str(invoice.total or 0)) - Decimal(str(get_paid_total(session, invoice.id))) > Decimal("0")
        for invoice in invoices
    )
    if allocation_summary is not None:
        next_action = "active_stay"
    elif reservation_summary is not None:
        next_action = "reservation_active"
    elif allocatable_invoices:
        next_action = "allocate_bed"
    elif payable_invoice_exists:
        next_action = "collect_payment"

    return TenantWorkspaceResponse(
        tenant=TenantListItem(
            id=int(tenant.id),
            name=tenant.name,
            email=tenant.email,
            phone=tenant.phone,
            status=tenant.status,
            room=tenant.room,
        ),
        invoices=invoice_summaries,
        payments=payment_summaries,
        receipts=receipt_summaries,
        active_reservation=reservation_summary,
        active_allocation=allocation_summary,
        timeline=get_tenant_timeline_rows(session, tenant.id),
        available_beds=available_beds,
        allocatable_invoices=allocatable_invoices,
        next_action=next_action,
    )
