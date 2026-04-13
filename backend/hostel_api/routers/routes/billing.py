from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bed, Block, Floor, Invoice, Payment, PaymentAllocation, Receipt, Room, Tenant
from app.services.common import format_money, get_base_currency, select_operational_bed_rows
from app.services.dashboard_metrics import get_dashboard_snapshot
from app.services.invoicing import (
    InvoiceValidationError,
    get_payment_unallocated_total,
    paid_totals_subquery,
    payment_allocations_for_payment_ids,
    payment_invoice_summary_text,
    record_tenant_payment,
)
from app.services.lifecycle import format_timestamp
from app.services.onboarding import apply_first_payment_conversion
from app.services.reservations import active_hold_reservations_subquery, expired_hold_invoice_ids_query
from app.services.settings import get_or_create_notification_settings
from ...deps import get_current_user, get_db_session
from ...schemas import (
    ActionResponse,
    BedOption,
    BillingInvoiceItem,
    BillingOverviewResponse,
    BillingPaymentItem,
    BillingReceiptItem,
    RecordTenantPaymentRequest,
    TenantListItem,
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


def _billing_invoice_item(
    invoice: Invoice,
    tenant: Tenant,
    currency: str,
    now: datetime,
    *,
    paid_total: Decimal | float | int = 0,
    hold_expires_at: datetime | None = None,
    hold_expired: bool = False,
) -> BillingInvoiceItem:
    paid_total = Decimal(str(paid_total or 0))
    total = Decimal(str(invoice.total or 0))
    balance = total - paid_total
    hold_hours_left: int | None = None
    if hold_expires_at is not None:
        if hold_expires_at.tzinfo is None:
            hold_expires_at = hold_expires_at.replace(tzinfo=now.tzinfo)
        hold_hours_left = max(math.ceil((hold_expires_at - now).total_seconds() / 3600), 0)
        hold_expired = False
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
        academic_year=invoice.academic_year.label if invoice.academic_year is not None else None,
    )


@router.get("/overview", response_model=BillingOverviewResponse)
def get_billing_overview(
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    invoice_status: str = Query(default="open"),
    invoice_limit: int = Query(default=40, ge=1, le=200),
    payment_limit: int = Query(default=20, ge=1, le=100),
    receipt_limit: int = Query(default=20, ge=1, le=100),
    _user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> BillingOverviewResponse:
    now = datetime.now(timezone.utc)
    currency = get_base_currency()
    settings = get_or_create_notification_settings(session)
    paid_totals = paid_totals_subquery()
    active_holds = active_hold_reservations_subquery()
    expired_holds = expired_hold_invoice_ids_query().subquery()
    snapshot = get_dashboard_snapshot(
        session,
        as_of=now,
        currency=currency,
        include_occupancy_tables=False,
        include_availability_rows=False,
        include_onboarding=False,
        include_alert_rows=False,
    )
    invoice_offset = (page - 1) * invoice_limit
    payment_offset = (page - 1) * payment_limit
    receipt_offset = (page - 1) * receipt_limit
    pattern = f"%{search.strip()}%" if search and search.strip() else None

    tenants = session.execute(select(Tenant).order_by(Tenant.name.asc()).limit(200)).scalars().all()
    bed_rows = session.execute(
        select_operational_bed_rows()
        .order_by(Block.name.asc(), Floor.floor_label.asc(), Room.room_code.asc(), Bed.bed_number.asc())
        .limit(100)
    ).all()

    invoice_query = (
        select(
            Invoice,
            Tenant,
            sa.func.coalesce(paid_totals.c.paid_total, 0).label("paid_total"),
            active_holds.c.expires_at.label("hold_expires_at"),
            expired_holds.c.invoice_id.is_not(None).label("hold_expired"),
        )
        .join(Tenant, Tenant.id == Invoice.tenant_id)
        .outerjoin(paid_totals, paid_totals.c.invoice_id == Invoice.id)
        .outerjoin(active_holds, active_holds.c.invoice_id == Invoice.id)
        .outerjoin(expired_holds, expired_holds.c.invoice_id == Invoice.id)
        .order_by(sa.func.coalesce(Invoice.issued_at, Invoice.created_at).desc(), Invoice.id.desc())
    )
    action_invoice_rows = session.execute(
        select(
            Invoice,
            Tenant,
            sa.func.coalesce(paid_totals.c.paid_total, 0).label("paid_total"),
            active_holds.c.expires_at.label("hold_expires_at"),
            expired_holds.c.invoice_id.is_not(None).label("hold_expired"),
        )
        .join(Tenant, Tenant.id == Invoice.tenant_id)
        .outerjoin(paid_totals, paid_totals.c.invoice_id == Invoice.id)
        .outerjoin(active_holds, active_holds.c.invoice_id == Invoice.id)
        .outerjoin(expired_holds, expired_holds.c.invoice_id == Invoice.id)
        .where(Invoice.status.in_(["draft", "submitted", "approved", "partially_paid"]))
        .order_by(sa.func.coalesce(Invoice.issued_at, Invoice.created_at).desc(), Invoice.id.desc())
        .limit(100)
    ).all()
    action_invoice_items = [
        _billing_invoice_item(
            invoice,
            tenant,
            currency,
            now,
            paid_total=paid_total,
            hold_expires_at=hold_expires_at,
            hold_expired=hold_expired,
        )
        for invoice, tenant, paid_total, hold_expires_at, hold_expired in action_invoice_rows
    ]
    if invoice_status == "open":
        invoice_query = invoice_query.where(Invoice.status.in_(["draft", "submitted", "approved", "partially_paid"]))
    elif invoice_status == "partial":
        invoice_query = invoice_query.where(Invoice.status == "partially_paid")
    elif invoice_status == "paid":
        invoice_query = invoice_query.where(Invoice.status == "paid")
    elif invoice_status != "all":
        invoice_query = invoice_query.where(Invoice.status.in_(["draft", "submitted", "approved", "partially_paid"]))
    if pattern:
        invoice_query = invoice_query.where(
            sa.or_(
                Tenant.name.ilike(pattern),
                Invoice.invoice_no.ilike(pattern),
                Invoice.status.ilike(pattern),
            )
        )
    invoice_total = session.execute(
        select(sa.func.count()).select_from(invoice_query.order_by(None).subquery())
    ).scalar_one()
    invoice_rows = session.execute(invoice_query.offset(invoice_offset).limit(invoice_limit)).all()
    invoice_items = [
        _billing_invoice_item(
            invoice,
            tenant,
            currency,
            now,
            paid_total=paid_total,
            hold_expires_at=hold_expires_at,
            hold_expired=hold_expired,
        )
        for invoice, tenant, paid_total, hold_expires_at, hold_expired in invoice_rows
    ]

    payment_query = (
        select(Payment, Tenant, Invoice)
        .join(Tenant, Tenant.id == Payment.tenant_id)
        .outerjoin(Invoice, Invoice.id == Payment.invoice_id)
        .order_by(sa.func.coalesce(Payment.paid_at, Payment.created_at).desc(), Payment.id.desc())
    )
    if pattern:
        payment_invoice_match = sa.exists(
            select(PaymentAllocation.id)
            .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
            .where(
                PaymentAllocation.payment_id == Payment.id,
                Invoice.invoice_no.ilike(pattern),
            )
        )
        payment_query = payment_query.where(
            sa.or_(
                Tenant.name.ilike(pattern),
                Payment.payment_no.ilike(pattern),
                Payment.reference.ilike(pattern),
                Invoice.invoice_no.ilike(pattern),
                payment_invoice_match,
            )
        )
    payment_total = session.execute(
        select(sa.func.count()).select_from(payment_query.order_by(None).subquery())
    ).scalar_one()
    payment_rows = session.execute(payment_query.offset(payment_offset).limit(payment_limit)).all()
    payment_allocation_map = payment_allocations_for_payment_ids(
        session,
        [int(payment.id) for payment, _tenant, _invoice in payment_rows],
    )

    receipt_query = (
        select(Receipt, Tenant, Payment, Invoice)
        .join(Tenant, Tenant.id == Receipt.tenant_id)
        .outerjoin(Payment, Payment.id == Receipt.payment_id)
        .outerjoin(Invoice, Invoice.id == Payment.invoice_id)
        .order_by(sa.func.coalesce(Receipt.issued_at, Receipt.created_at).desc(), Receipt.id.desc())
    )
    if pattern:
        receipt_invoice_match = sa.exists(
            select(PaymentAllocation.id)
            .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
            .where(
                PaymentAllocation.payment_id == Payment.id,
                Invoice.invoice_no.ilike(pattern),
            )
        )
        receipt_query = receipt_query.where(
            sa.or_(
                Tenant.name.ilike(pattern),
                Receipt.receipt_no.ilike(pattern),
                Payment.payment_no.ilike(pattern),
                Invoice.invoice_no.ilike(pattern),
                receipt_invoice_match,
            )
        )
    receipt_total = session.execute(
        select(sa.func.count()).select_from(receipt_query.order_by(None).subquery())
    ).scalar_one()
    receipt_rows = session.execute(receipt_query.offset(receipt_offset).limit(receipt_limit)).all()
    receipt_allocation_map = payment_allocations_for_payment_ids(
        session,
        [int(payment.id) for _receipt, _tenant, payment, _invoice in receipt_rows if payment is not None],
    )

    payment_items = [
        BillingPaymentItem(
            id=int(payment.id),
            payment_no=payment.payment_no,
            tenant_id=int(tenant.id),
            tenant_name=tenant.name,
            invoice_id=int(invoice.id) if invoice is not None else None,
            invoice_no=invoice.invoice_no if invoice is not None else None,
            amount=format_money(payment.amount, payment.currency),
            method=payment.method,
            reference=payment.reference,
            status=payment.status,
            paid_at=format_timestamp(payment.paid_at or payment.created_at),
            can_void=payment.status == "completed",
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
        for payment, tenant, invoice in payment_rows
    ]

    receipt_items = [
        BillingReceiptItem(
            id=int(receipt.id),
            receipt_no=receipt.receipt_no,
            tenant_id=int(tenant.id),
            tenant_name=tenant.name,
            payment_id=int(payment.id) if payment is not None else None,
            payment_no=payment.payment_no if payment is not None else None,
            invoice_id=int(invoice.id) if invoice is not None else None,
            invoice_no=invoice.invoice_no if invoice is not None else None,
            amount=format_money(receipt.amount, receipt.currency),
            issued_at=format_timestamp(receipt.issued_at or receipt.created_at),
            printed_count=int(receipt.printed_count or 0),
            academic_year=receipt.academic_year.label if receipt.academic_year is not None else None,
            invoice_summary=(
                payment_invoice_summary_text(
                    session,
                    int(payment.id),
                    allocation_map=receipt_allocation_map,
                )
                if payment is not None
                else "-"
            ),
        )
        for receipt, tenant, payment, invoice in receipt_rows
    ]

    payable_invoice_rows = session.execute(
        select(
            Invoice,
            Tenant,
            sa.func.coalesce(paid_totals.c.paid_total, 0).label("paid_total"),
            active_holds.c.expires_at.label("hold_expires_at"),
            expired_holds.c.invoice_id.is_not(None).label("hold_expired"),
        )
        .join(Tenant, Tenant.id == Invoice.tenant_id)
        .outerjoin(paid_totals, paid_totals.c.invoice_id == Invoice.id)
        .outerjoin(active_holds, active_holds.c.invoice_id == Invoice.id)
        .outerjoin(expired_holds, expired_holds.c.invoice_id == Invoice.id)
        .where(
            Invoice.status.in_(["approved", "partially_paid"]),
            ~Invoice.id.in_(expired_hold_invoice_ids_query()),
        )
        .order_by(sa.func.coalesce(Invoice.issued_at, Invoice.created_at).desc(), Invoice.id.desc())
        .limit(100)
    ).all()
    payable_invoices = [
        _billing_invoice_item(
            invoice,
            tenant,
            currency,
            now,
            paid_total=paid_total,
            hold_expires_at=hold_expires_at,
            hold_expired=hold_expired,
        )
        for invoice, tenant, paid_total, hold_expires_at, hold_expired in payable_invoice_rows
    ]

    submitted_rows = session.execute(
        select(
            Invoice,
            Tenant,
            sa.func.coalesce(paid_totals.c.paid_total, 0).label("paid_total"),
            active_holds.c.expires_at.label("hold_expires_at"),
            expired_holds.c.invoice_id.is_not(None).label("hold_expired"),
        )
        .join(Tenant, Tenant.id == Invoice.tenant_id)
        .outerjoin(paid_totals, paid_totals.c.invoice_id == Invoice.id)
        .outerjoin(active_holds, active_holds.c.invoice_id == Invoice.id)
        .outerjoin(expired_holds, expired_holds.c.invoice_id == Invoice.id)
        .where(Invoice.status == "submitted")
        .order_by(Invoice.created_at.asc(), Invoice.id.asc())
        .limit(100)
    ).all()
    submitted_invoices = [
        _billing_invoice_item(
            invoice,
            tenant,
            currency,
            now,
            paid_total=paid_total,
            hold_expires_at=hold_expires_at,
            hold_expired=hold_expired,
        )
        for invoice, tenant, paid_total, hold_expires_at, hold_expired in submitted_rows
    ]

    return BillingOverviewResponse(
        outstanding_total=format_money(snapshot.finance.outstanding, currency),
        collected_mtd=format_money(snapshot.finance.collected_mtd, currency),
        action_invoice_rows=action_invoice_items,
        invoice_rows=invoice_items,
        invoice_total=int(invoice_total or 0),
        payment_rows=payment_items,
        payment_total=int(payment_total or 0),
        receipt_rows=receipt_items,
        receipt_total=int(receipt_total or 0),
        tenants=[
            TenantListItem(
                id=int(tenant.id),
                name=tenant.name,
                email=tenant.email,
                phone=tenant.phone,
                status=tenant.status,
                room=tenant.room,
            )
            for tenant in tenants
        ],
        available_beds=[_bed_option(bed, room, floor, block) for bed, room, floor, block in bed_rows],
        payable_invoices=payable_invoices,
        submitted_invoices=submitted_invoices,
        default_hold_hours=int(settings.reservation_default_hold_hours or 24),
        block_duplicate_payment_reference=bool(settings.block_duplicate_payment_reference),
        auto_approve_invoices=bool(settings.auto_approve_invoices),
    )


@router.post("/payments", response_model=ActionResponse)
def record_tenant_payment_route(
    payload: RecordTenantPaymentRequest,
    session: Session = Depends(get_db_session),
    user: dict = Depends(get_current_user),
) -> ActionResponse:
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
        payment, receipt, invoice_totals = record_tenant_payment(
            session,
            tenant_id=payload.tenant_id,
            user_id=int(user["id"]),
            amount=payload.amount,
            method=payload.method,
            reference=reference or None,
            allocations=[allocation.model_dump() for allocation in payload.allocations],
            now=now,
        )
    except InvoiceValidationError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    first_invoice_id = next(iter(invoice_totals.keys()), None)
    conversion_message = None
    if first_invoice_id is not None:
        conversion = apply_first_payment_conversion(
            session,
            tenant_id=int(payload.tenant_id),
            invoice_id=int(first_invoice_id),
            user_id=int(user["id"]),
            now=now,
        )
        if conversion.activated:
            conversion_message = "Payment recorded. Tenant activated on first payment."

    session.commit()
    return ActionResponse(
        message=conversion_message or "Payment recorded.",
        warning_message=(
            "Payment recorded with a duplicate reference because duplicate blocking is set to warn only. Review the ledger entry."
            if duplicate_reference_detected
            else None
        ),
        tenant_id=int(payload.tenant_id),
        invoice_id=int(first_invoice_id) if first_invoice_id is not None and len(invoice_totals) == 1 else None,
        payment_id=int(payment.id),
        receipt_id=int(receipt.id),
    )
