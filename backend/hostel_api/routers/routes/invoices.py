from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bed, BedReservation, Block, Floor, Invoice, InvoiceEvent, Payment, Receipt, Room, Tenant
from app.services.allocations import assign_bed_for_paid_invoice
from app.services.common import combine_date, format_money, get_base_currency
from app.services.invoicing import (
    InvoiceValidationError,
    cancel_invoice,
    create_invoice,
    get_paid_total,
    record_payment,
    update_invoice_details,
    void_payment,
)
from app.services.lifecycle import format_timestamp
from app.services.onboarding import apply_first_payment_conversion
from app.services.reservations import (
    invoice_hold_expired,
    invoice_hold_snapshot,
    release_reservation_on_payment,
    reserve_bed_for_invoice,
)
from app.services.settings import get_or_create_notification_settings
from ...deps import get_current_user, get_db_session, require_admin
from ...schemas import (
    ActionResponse,
    AssignBedRequest,
    BedOption,
    BillingInvoiceItem,
    CreateInvoiceRequest,
    InvoiceDetailResponse,
    PaymentSummary,
    ReceiptSummary,
    RecordPaymentRequest,
    RejectInvoiceRequest,
    TenantListItem,
    UpdateInvoiceRequest,
    VoidPaymentRequest,
)

router = APIRouter()


def _log_invoice_event(session: Session, invoice_id: int, event_type: str, payload: dict[str, object]) -> None:
    session.add(InvoiceEvent(invoice_id=invoice_id, event_type=event_type, payload=payload))


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


def _billing_invoice_item(session: Session, invoice: Invoice, tenant: Tenant, currency: str) -> BillingInvoiceItem:
    paid_total = Decimal(str(get_paid_total(session, int(invoice.id))))
    total = Decimal(str(invoice.total or 0))
    balance = total - paid_total
    hold_expires_at, hold_hours_left, hold_expired = invoice_hold_snapshot(
        session,
        int(invoice.id),
        now=datetime.now(timezone.utc),
    )
    return BillingInvoiceItem(
        id=int(invoice.id),
        invoice_no=invoice.invoice_no,
        tenant_id=int(tenant.id),
        tenant_name=tenant.name,
        status=invoice.status,
        total=format_money(total, currency),
        paid_total=format_money(paid_total, currency),
        balance=format_money(balance, currency),
        issued_at=format_timestamp(invoice.issued_at),
        due_at=format_timestamp(invoice.due_at),
        hold_expired=hold_expired,
        hold_expires_at=format_timestamp(hold_expires_at),
        hold_hours_left=hold_hours_left,
    )


@router.post("", response_model=ActionResponse)
def create_invoice_route(
    payload: CreateInvoiceRequest,
    session: Session = Depends(get_db_session),
    user: dict = Depends(get_current_user),
) -> ActionResponse:
    currency = get_base_currency()
    now = datetime.now(timezone.utc)
    settings = get_or_create_notification_settings(session)
    invoice_status = "approved" if payload.submit_now and bool(settings.auto_approve_invoices) else ("submitted" if payload.submit_now else "draft")
    try:
        invoice = create_invoice(
            session,
            tenant_id=payload.tenant_id,
            user_id=int(user["id"]),
            reserved_bed_id=payload.reserved_bed_id,
            currency=currency,
            tax=payload.tax,
            discount=payload.discount,
            notes=payload.notes.strip() or None,
            status=invoice_status,
            due_at=combine_date(payload.due_at),
            hold_until=now + timedelta(hours=int(payload.hold_hours)),
            now=now,
        )
    except (InvoiceValidationError, ValueError) as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _log_invoice_event(
        session,
        int(invoice.id),
        "created",
        {
            "user_id": int(user["id"]),
            "tenant_id": int(invoice.tenant_id),
            "bed_id": int(invoice.reserved_bed_id) if invoice.reserved_bed_id is not None else None,
            "status": invoice.status,
            "at": now.isoformat(),
        },
    )
    if payload.submit_now:
        _log_invoice_event(
            session,
            int(invoice.id),
            "submitted" if invoice.status == "submitted" else "approved",
            {
                "user_id": int(user["id"]),
                "tenant_id": int(invoice.tenant_id),
                "bed_id": int(invoice.reserved_bed_id) if invoice.reserved_bed_id is not None else None,
                "auto_approved": bool(invoice.status == "approved"),
                "at": now.isoformat(),
            },
        )
    session.commit()
    return ActionResponse(
        message="Invoice created.",
        invoice_id=int(invoice.id),
    )


@router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
def get_invoice_detail(
    invoice_id: int,
    _user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> InvoiceDetailResponse:
    currency = get_base_currency()
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    tenant = session.get(Tenant, invoice.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    invoice_item = _billing_invoice_item(session, invoice, tenant, currency)

    payments = session.execute(
        select(Payment).where(Payment.invoice_id == invoice.id).order_by(sa.func.coalesce(Payment.paid_at, Payment.created_at).desc())
    ).scalars().all()
    receipts = session.execute(
        select(Receipt).join(Payment, Payment.id == Receipt.payment_id).where(Payment.invoice_id == invoice.id).order_by(sa.func.coalesce(Receipt.issued_at, Receipt.created_at).desc())
    ).scalars().all()
    bed_rows = session.execute(
        select(Bed, Room, Floor, Block)
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .where(Bed.status == "AVAILABLE")
        .order_by(Block.name.asc(), Floor.floor_label.asc(), Room.room_code.asc(), Bed.bed_number.asc())
        .limit(100)
    ).all()

    reserved_bed_label = None
    if invoice.reserved_bed_id is not None:
        reserved_row = session.execute(
            select(Bed, Room, Floor, Block)
            .join(Room, Room.id == Bed.room_id)
            .join(Block, Block.id == Room.block_id)
            .outerjoin(Floor, Floor.id == Room.floor_id)
            .where(Bed.id == invoice.reserved_bed_id)
        ).first()
        if reserved_row:
            bed, room, floor, block = reserved_row
            reserved_bed_label = _bed_option(bed, room, floor, block).label

    return InvoiceDetailResponse(
        invoice=invoice_item,
        tenant=TenantListItem(
            id=int(tenant.id),
            name=tenant.name,
            email=tenant.email,
            phone=tenant.phone,
            status=tenant.status,
        ),
        payments=[
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
        ],
        receipts=[
            ReceiptSummary(
                id=int(receipt.id),
                receipt_no=receipt.receipt_no,
                amount=format_money(receipt.amount, receipt.currency),
                issued_at=format_timestamp(receipt.issued_at or receipt.created_at),
                printed_count=int(receipt.printed_count or 0),
            )
            for receipt in receipts
        ],
        available_beds=[_bed_option(bed, room, floor, block) for bed, room, floor, block in bed_rows],
        reserved_bed_label=reserved_bed_label,
        reserved_bed_id=int(invoice.reserved_bed_id) if invoice.reserved_bed_id is not None else None,
        hold_expired=invoice_item.hold_expired,
        subtotal=format_money(invoice.subtotal, invoice.currency),
        tax=format_money(invoice.tax, invoice.currency),
        discount=format_money(invoice.discount, invoice.currency),
        notes=invoice.notes,
        can_edit=invoice.status in {"draft", "submitted", "approved", "partially_paid"}
        and Decimal(str(get_paid_total(session, int(invoice.id)))) == Decimal("0"),
        can_cancel=invoice.status not in {"paid", "cancelled"}
        and Decimal(str(get_paid_total(session, int(invoice.id)))) == Decimal("0"),
    )


@router.post("/{invoice_id}/update", response_model=ActionResponse)
def update_invoice_route(
    invoice_id: int,
    payload: UpdateInvoiceRequest,
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")
    now = datetime.now(timezone.utc)
    try:
        updated_invoice = update_invoice_details(
            session,
            invoice=invoice,
            user_id=int(user["id"]),
            reserved_bed_id=payload.reserved_bed_id,
            tax=payload.tax,
            discount=payload.discount,
            notes=payload.notes.strip() or None,
            due_at=combine_date(payload.due_at),
            hold_until=now + timedelta(hours=int(payload.hold_hours)),
            now=now,
        )
    except InvoiceValidationError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _log_invoice_event(
        session,
        int(updated_invoice.id),
        "updated",
        {
            "user_id": int(user["id"]),
            "bed_id": int(updated_invoice.reserved_bed_id) if updated_invoice.reserved_bed_id is not None else None,
            "at": now.isoformat(),
        },
    )
    session.commit()
    return ActionResponse(message="Invoice updated.", invoice_id=int(updated_invoice.id))


@router.post("/{invoice_id}/approve", response_model=ActionResponse)
def approve_invoice(
    invoice_id: int,
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")
    if invoice.status != "submitted":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice is not eligible for approval.")
    if invoice.reserved_bed_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice has no active bed hold. Select a new bed before approval.",
        )

    invoice.status = "approved"
    if invoice.reserved_bed_id:
        existing_reservation = session.execute(
            select(BedReservation.id).where(
                BedReservation.invoice_id == invoice.id,
                BedReservation.status == "ACTIVE",
            ).limit(1)
        ).scalar_one_or_none()
        if existing_reservation is None:
            settings = get_or_create_notification_settings(session)
            now = datetime.now(timezone.utc)
            try:
                reserve_bed_for_invoice(
                    session,
                    invoice_id=int(invoice.id),
                    tenant_id=int(invoice.tenant_id),
                    bed_id=int(invoice.reserved_bed_id),
                    hold_until=now + timedelta(hours=int(settings.reservation_default_hold_hours or 24)),
                    user_id=int(user["id"]),
                    now=now,
                )
            except ValueError as exc:
                session.rollback()
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _log_invoice_event(
        session,
        int(invoice.id),
        "approved",
        {
            "user_id": int(user["id"]),
            "tenant_id": int(invoice.tenant_id),
            "bed_id": int(invoice.reserved_bed_id) if invoice.reserved_bed_id is not None else None,
            "at": datetime.now(timezone.utc).isoformat(),
        },
    )
    session.commit()
    return ActionResponse(message="Invoice approved.", invoice_id=int(invoice.id))


@router.post("/{invoice_id}/reject", response_model=ActionResponse)
def reject_invoice(
    invoice_id: int,
    payload: RejectInvoiceRequest,
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")
    if invoice.status != "submitted":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice is not eligible for rejection.")

    invoice.status = "rejected"
    release_reservation_on_payment(
        session,
        invoice_id=int(invoice.id),
        user_id=int(user["id"]),
        now=datetime.now(timezone.utc),
        reason=payload.reason.strip() or "Invoice rejected",
    )
    _log_invoice_event(
        session,
        int(invoice.id),
        "rejected",
        {
            "user_id": int(user["id"]),
            "tenant_id": int(invoice.tenant_id),
            "bed_id": int(invoice.reserved_bed_id) if invoice.reserved_bed_id is not None else None,
            "reason": payload.reason.strip() or None,
            "at": datetime.now(timezone.utc).isoformat(),
        },
    )
    session.commit()
    return ActionResponse(message="Invoice rejected.", invoice_id=int(invoice.id))


@router.post("/{invoice_id}/cancel", response_model=ActionResponse)
def cancel_invoice_route(
    invoice_id: int,
    payload: RejectInvoiceRequest,
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")
    now = datetime.now(timezone.utc)
    try:
        cancel_invoice(
            session,
            invoice=invoice,
            user_id=int(user["id"]),
            reason=payload.reason,
            now=now,
        )
    except InvoiceValidationError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _log_invoice_event(
        session,
        int(invoice.id),
        "cancelled",
        {
            "user_id": int(user["id"]),
            "reason": payload.reason.strip() or None,
            "at": now.isoformat(),
        },
    )
    session.commit()
    return ActionResponse(message="Invoice cancelled.", invoice_id=int(invoice.id))


@router.post("/{invoice_id}/payments", response_model=ActionResponse)
def record_invoice_payment(
    invoice_id: int,
    payload: RecordPaymentRequest,
    session: Session = Depends(get_db_session),
    user: dict = Depends(get_current_user),
) -> ActionResponse:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")
    if invoice.status not in {"approved", "partially_paid"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice is not payable.")
    if invoice_hold_expired(session, int(invoice.id)) or invoice.reserved_bed_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice has no active bed hold. Select a new bed before recording payment.",
        )

    reference = payload.reference.strip()
    if payload.method != "cash" and not reference:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reference is required for non-cash methods.")

    settings = get_or_create_notification_settings(session)
    duplicate_reference_detected = False
    if reference:
        duplicate = session.execute(
            select(Payment.id).where(Payment.reference.ilike(reference)).limit(1)
        ).scalar_one_or_none()
        if duplicate is not None:
            if bool(settings.block_duplicate_payment_reference):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate reference blocking is enabled.")
            duplicate_reference_detected = True

    now = datetime.now(timezone.utc)
    try:
        payment, receipt, _ = record_payment(
            session,
            invoice=invoice,
            user_id=int(user["id"]),
            amount=payload.amount,
            method=payload.method,
            reference=reference or None,
            now=now,
        )
    except InvoiceValidationError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _log_invoice_event(
        session,
        int(invoice.id),
        "payment_received",
        {
            "user_id": int(user["id"]),
            "tenant_id": int(invoice.tenant_id),
            "bed_id": int(invoice.reserved_bed_id) if invoice.reserved_bed_id is not None else None,
            "amount": str(payload.amount),
            "method": payload.method,
            "at": now.isoformat(),
        },
    )
    conversion = apply_first_payment_conversion(
        session,
        tenant_id=int(invoice.tenant_id),
        invoice_id=int(invoice.id),
        user_id=int(user["id"]),
        now=now,
    )
    session.commit()
    message = "Payment recorded."
    if conversion.activated:
        message = "Payment recorded. Tenant activated on first payment."
    return ActionResponse(
        message=message,
        warning_message=(
            "Payment recorded with a duplicate reference because duplicate blocking is set to warn only. Review the ledger entry."
            if duplicate_reference_detected
            else None
        ),
        invoice_id=int(invoice.id),
        payment_id=int(payment.id),
        receipt_id=int(receipt.id),
    )


@router.post("/payments/{payment_id}/void", response_model=ActionResponse)
def void_payment_route(
    payment_id: int,
    payload: VoidPaymentRequest,
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found.")
    settings = get_or_create_notification_settings(session)
    now = datetime.now(timezone.utc)
    try:
        void_payment(
            session,
            payment=payment,
            user_id=int(user["id"]),
            reason=payload.reason,
            hold_until=now + timedelta(hours=int(settings.reservation_default_hold_hours or 24)),
            now=now,
        )
    except InvoiceValidationError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if payment.invoice_id is not None:
        _log_invoice_event(
            session,
            int(payment.invoice_id),
            "payment_voided",
            {
                "user_id": int(user["id"]),
                "payment_id": int(payment.id),
                "reason": payload.reason.strip() or None,
                "at": now.isoformat(),
            },
        )
    session.commit()
    return ActionResponse(
        message="Payment voided.",
        payment_id=int(payment.id),
        invoice_id=int(payment.invoice_id) if payment.invoice_id is not None else None,
    )


@router.post("/{invoice_id}/allocate", response_model=ActionResponse)
def allocate_invoice_bed(
    invoice_id: int,
    payload: AssignBedRequest,
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    try:
        result = assign_bed_for_paid_invoice(
            session,
            invoice_id=invoice_id,
            bed_id=payload.bed_id,
            user_id=int(user["id"]),
            now=datetime.now(timezone.utc),
        )
        session.commit()
    except PermissionError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ActionResponse(
        message="Bed assigned successfully.",
        invoice_id=int(result.invoice_id),
        allocation_id=int(result.allocation_id),
        bed_id=int(result.bed_id),
    )
