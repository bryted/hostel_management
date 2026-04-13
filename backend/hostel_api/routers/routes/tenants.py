from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, Bed, BedReservation, Block, Floor, Invoice, Payment, Receipt, Room, Tenant
from app.services.common import format_money, get_base_currency, select_operational_bed_rows
from app.services.invoicing import (
    get_payment_unallocated_total,
    paid_totals_subquery,
    payment_allocations_for_payment_ids,
    payment_invoice_summary_text,
)
from app.services.lifecycle import (
    _log_tenant_event,
    derive_tenant_status,
    format_timestamp,
    get_tenant_timeline_rows,
    get_tenant_workflow_flags,
)
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
    TenantListResponse,
    TenantWorkspaceResponse,
    UpdateTenantRequest,
)

router = APIRouter()

VALID_TENANT_STATUSES = {"prospect", "active", "inactive"}
WORKSPACE_PAGE_SIZE = 20


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
    invoice: Invoice,
    currency: str,
    allocated_invoice_ids: set[int],
    paid_total: Decimal | float | int = 0,
) -> InvoiceSummary:
    paid_total = Decimal(str(paid_total or 0))
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
        academic_year=invoice.academic_year.label if invoice.academic_year is not None else None,
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


def _paged_rows(session: Session, query: sa.Select, *, page: int, page_size: int) -> tuple[int, list[object]]:
    total = int(
        session.execute(select(sa.func.count()).select_from(query.order_by(None).subquery())).scalar_one() or 0
    )
    rows = session.execute(query.offset((page - 1) * page_size).limit(page_size)).all()
    return total, rows


def _validate_tenant_status_change(
    session: Session,
    *,
    tenant_id: int | None,
    current_status: str | None,
    target_status: str,
    user: dict,
) -> None:
    current_status = (current_status or "").strip().lower()
    if target_status == current_status:
        return
    if target_status in {"active", "inactive"} and not bool(user.get("is_admin")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can activate or archive tenants.",
        )
    if tenant_id is None:
        if target_status == "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New tenants cannot start as active. Record payment or confirm allocation first.",
            )
        return

    flags = get_tenant_workflow_flags(session, tenant_id)
    derived_status = derive_tenant_status(session, tenant_id)
    if target_status == "active" and derived_status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant can only be marked active after payment or confirmed allocation.",
        )
    if target_status == "inactive" and derived_status != "inactive":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End active stays, release holds, and close unsettled invoices before archiving this tenant.",
        )
    if target_status == "prospect" and (
        flags["has_confirmed_allocation"] or flags["has_paid_unallocated_invoice"]
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant with live payment or allocation workflow cannot be moved back to prospect manually.",
        )


@router.get("", response_model=TenantListResponse)
def list_tenants(
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    _user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> TenantListResponse:
    query = select(
        Tenant.id,
        Tenant.name,
        Tenant.email,
        Tenant.phone,
        Tenant.status,
        Tenant.room,
    )
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(
            sa.or_(
                Tenant.name.ilike(pattern),
                Tenant.email.ilike(pattern),
                Tenant.phone.ilike(pattern),
                Tenant.normalized_phone.ilike(pattern),
            )
        )
    filtered = query.subquery()
    summary = session.execute(
        select(
            sa.func.count().label("total"),
            sa.func.coalesce(sa.func.sum(sa.case((filtered.c.status == "active", 1), else_=0)), 0).label("active_total"),
            sa.func.coalesce(sa.func.sum(sa.case((filtered.c.status == "prospect", 1), else_=0)), 0).label("prospect_total"),
            sa.func.coalesce(sa.func.sum(sa.case((filtered.c.status == "inactive", 1), else_=0)), 0).label("inactive_total"),
        )
    ).one()
    tenant_rows = session.execute(
        select(filtered)
        .order_by(filtered.c.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return TenantListResponse(
        rows=[
            TenantListItem(
                id=int(row.id),
                name=row.name,
                email=row.email,
                phone=row.phone,
                status=row.status,
                room=row.room,
            )
            for row in tenant_rows
        ],
        total=int(summary.total or 0),
        page=page,
        page_size=page_size,
        active_total=int(summary.active_total or 0),
        prospect_total=int(summary.prospect_total or 0),
        inactive_total=int(summary.inactive_total or 0),
    )


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
    _validate_tenant_status_change(
        session,
        tenant_id=None,
        current_status=None,
        target_status=status_value,
        user=user,
    )
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
    _validate_tenant_status_change(
        session,
        tenant_id=int(tenant.id),
        current_status=tenant.status,
        target_status=status_value,
        user=user,
    )
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
    if not bool(user.get("is_admin")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    _validate_tenant_status_change(
        session,
        tenant_id=int(tenant.id),
        current_status=tenant.status,
        target_status="inactive",
        user=user,
    )
    tenant.status = "inactive"
    _log_tenant_event(session, int(tenant.id), "TENANT_ARCHIVED", int(user["id"]), {})
    session.commit()
    return ActionResponse(message="Tenant archived.", tenant_id=int(tenant.id))


@router.get("/{tenant_id}/workspace", response_model=TenantWorkspaceResponse)
def tenant_workspace(
    tenant_id: int,
    invoice_page: int = Query(default=1, ge=1),
    payment_page: int = Query(default=1, ge=1),
    receipt_page: int = Query(default=1, ge=1),
    timeline_page: int = Query(default=1, ge=1),
    _user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> TenantWorkspaceResponse:
    currency = get_base_currency()
    paid_totals = paid_totals_subquery()
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    invoice_total, invoices = _paged_rows(
        session,
        select(Invoice, sa.func.coalesce(paid_totals.c.paid_total, 0).label("paid_total"))
        .outerjoin(paid_totals, paid_totals.c.invoice_id == Invoice.id)
        .where(Invoice.tenant_id == tenant.id)
        .order_by(Invoice.created_at.desc()),
        page=invoice_page,
        page_size=WORKSPACE_PAGE_SIZE,
    )
    payment_total, payment_rows = _paged_rows(
        session,
        select(Payment)
        .where(Payment.tenant_id == tenant.id)
        .order_by(sa.func.coalesce(Payment.paid_at, Payment.created_at).desc()),
        page=payment_page,
        page_size=WORKSPACE_PAGE_SIZE,
    )
    payments = [payment for (payment,) in payment_rows]
    payment_allocation_map = payment_allocations_for_payment_ids(session, [int(payment.id) for payment in payments])
    receipt_total, receipt_rows = _paged_rows(
        session,
        select(Receipt)
        .where(Receipt.tenant_id == tenant.id)
        .order_by(sa.func.coalesce(Receipt.issued_at, Receipt.created_at).desc()),
        page=receipt_page,
        page_size=WORKSPACE_PAGE_SIZE,
    )
    receipts = [receipt for (receipt,) in receipt_rows]
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

    invoice_summaries = [
        _build_invoice_summary(invoice, currency, allocated_invoice_ids, paid_total)
        for invoice, paid_total in invoices
    ]
    allocatable_invoices = [invoice for invoice in invoice_summaries if invoice.can_allocate]

    bed_rows = session.execute(
        select_operational_bed_rows()
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
            academic_year=payment.academic_year.label if payment.academic_year is not None else None,
            invoice_summary=payment_invoice_summary_text(
                session,
                int(payment.id),
                allocation_map=payment_allocation_map,
            ),
            allocated_total=format_money(
                Decimal(str(payment.amount or 0)) - get_payment_unallocated_total(session, payment),
                payment.currency,
            ),
            unallocated_amount=format_money(get_payment_unallocated_total(session, payment), payment.currency),
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
            academic_year=receipt.academic_year.label if receipt.academic_year is not None else None,
            invoice_summary=payment_invoice_summary_text(
                session,
                int(receipt.payment_id),
                allocation_map=payment_allocation_map,
            )
            if receipt.payment_id is not None
            else "-",
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
            academic_year=reservation.academic_year.label if reservation.academic_year is not None else None,
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
            academic_year=allocation.academic_year.label if allocation.academic_year is not None else None,
        )

    next_action = "review_billing"
    payable_invoice_exists = session.execute(
        select(Invoice.id)
        .outerjoin(paid_totals, paid_totals.c.invoice_id == Invoice.id)
        .where(
            Invoice.tenant_id == tenant.id,
            Invoice.status.not_in({"draft", "rejected"}),
            sa.func.coalesce(Invoice.total, 0) - sa.func.coalesce(paid_totals.c.paid_total, 0) > 0,
        )
        .limit(1)
    ).scalar_one_or_none() is not None
    if allocation_summary is not None:
        next_action = "active_stay"
    elif reservation_summary is not None:
        next_action = "reservation_active"
    elif allocatable_invoices:
        next_action = "allocate_bed"
    elif payable_invoice_exists:
        next_action = "collect_payment"

    timeline_total, timeline_rows = get_tenant_timeline_rows(
        session,
        tenant.id,
        page=timeline_page,
        page_size=WORKSPACE_PAGE_SIZE,
    )

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
        invoice_total=invoice_total,
        invoice_page=invoice_page,
        invoice_page_size=WORKSPACE_PAGE_SIZE,
        payments=payment_summaries,
        payment_total=payment_total,
        payment_page=payment_page,
        payment_page_size=WORKSPACE_PAGE_SIZE,
        receipts=receipt_summaries,
        receipt_total=receipt_total,
        receipt_page=receipt_page,
        receipt_page_size=WORKSPACE_PAGE_SIZE,
        active_reservation=reservation_summary,
        active_allocation=allocation_summary,
        timeline=timeline_rows,
        timeline_total=timeline_total,
        timeline_page=timeline_page,
        timeline_page_size=WORKSPACE_PAGE_SIZE,
        available_beds=available_beds,
        allocatable_invoices=allocatable_invoices,
        next_action=next_action,
    )
