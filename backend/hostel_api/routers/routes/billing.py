from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bed, Block, Floor, Invoice, Payment, Receipt, Room, Tenant
from app.services.common import format_money, get_base_currency
from app.services.dashboard_metrics import get_dashboard_snapshot
from app.services.invoicing import get_paid_total
from app.services.lifecycle import format_timestamp
from app.services.reservations import expired_hold_invoice_ids_query, invoice_hold_snapshot
from app.services.settings import get_or_create_notification_settings
from ...deps import get_current_user, get_db_session
from ...schemas import BedOption, BillingInvoiceItem, BillingOverviewResponse, BillingPaymentItem, BillingReceiptItem, TenantListItem

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
    session: Session,
    invoice: Invoice,
    tenant: Tenant,
    currency: str,
    now: datetime,
) -> BillingInvoiceItem:
    paid_total = Decimal(str(get_paid_total(session, int(invoice.id))))
    total = Decimal(str(invoice.total or 0))
    balance = total - paid_total
    hold_expires_at, hold_hours_left, hold_expired = invoice_hold_snapshot(
        session,
        int(invoice.id),
        now=now,
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
    snapshot = get_dashboard_snapshot(
        session,
        as_of=now,
        currency=currency,
        include_occupancy_tables=False,
    )
    invoice_offset = (page - 1) * invoice_limit
    payment_offset = (page - 1) * payment_limit
    receipt_offset = (page - 1) * receipt_limit
    pattern = f"%{search.strip()}%" if search and search.strip() else None

    tenants = session.execute(select(Tenant).order_by(Tenant.name.asc()).limit(200)).scalars().all()
    bed_rows = session.execute(
        select(Bed, Room, Floor, Block)
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .where(Bed.status == "AVAILABLE")
        .order_by(Block.name.asc(), Floor.floor_label.asc(), Room.room_code.asc(), Bed.bed_number.asc())
        .limit(100)
    ).all()

    invoice_query = (
        select(Invoice, Tenant)
        .join(Tenant, Tenant.id == Invoice.tenant_id)
        .order_by(sa.func.coalesce(Invoice.issued_at, Invoice.created_at).desc(), Invoice.id.desc())
    )
    action_invoice_rows = session.execute(
        select(Invoice, Tenant)
        .join(Tenant, Tenant.id == Invoice.tenant_id)
        .where(Invoice.status.in_(["draft", "submitted", "approved", "partially_paid"]))
        .order_by(sa.func.coalesce(Invoice.issued_at, Invoice.created_at).desc(), Invoice.id.desc())
        .limit(100)
    ).all()
    action_invoice_items = [
        _billing_invoice_item(session, invoice, tenant, currency, now)
        for invoice, tenant in action_invoice_rows
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
    invoice_items = [_billing_invoice_item(session, invoice, tenant, currency, now) for invoice, tenant in invoice_rows]

    payment_query = (
        select(Payment, Tenant, Invoice)
        .join(Tenant, Tenant.id == Payment.tenant_id)
        .outerjoin(Invoice, Invoice.id == Payment.invoice_id)
        .order_by(sa.func.coalesce(Payment.paid_at, Payment.created_at).desc(), Payment.id.desc())
    )
    if pattern:
        payment_query = payment_query.where(
            sa.or_(
                Tenant.name.ilike(pattern),
                Payment.payment_no.ilike(pattern),
                Payment.reference.ilike(pattern),
                Invoice.invoice_no.ilike(pattern),
            )
        )
    payment_total = session.execute(
        select(sa.func.count()).select_from(payment_query.order_by(None).subquery())
    ).scalar_one()
    payment_rows = session.execute(payment_query.offset(payment_offset).limit(payment_limit)).all()

    receipt_query = (
        select(Receipt, Tenant, Payment, Invoice)
        .join(Tenant, Tenant.id == Receipt.tenant_id)
        .outerjoin(Payment, Payment.id == Receipt.payment_id)
        .outerjoin(Invoice, Invoice.id == Payment.invoice_id)
        .order_by(sa.func.coalesce(Receipt.issued_at, Receipt.created_at).desc(), Receipt.id.desc())
    )
    if pattern:
        receipt_query = receipt_query.where(
            sa.or_(
                Tenant.name.ilike(pattern),
                Receipt.receipt_no.ilike(pattern),
                Payment.payment_no.ilike(pattern),
                Invoice.invoice_no.ilike(pattern),
            )
        )
    receipt_total = session.execute(
        select(sa.func.count()).select_from(receipt_query.order_by(None).subquery())
    ).scalar_one()
    receipt_rows = session.execute(receipt_query.offset(receipt_offset).limit(receipt_limit)).all()

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
        )
        for receipt, tenant, payment, invoice in receipt_rows
    ]

    payable_invoice_rows = session.execute(
        select(Invoice, Tenant)
        .join(Tenant, Tenant.id == Invoice.tenant_id)
        .where(
            Invoice.status.in_(["approved", "partially_paid"]),
            ~Invoice.id.in_(expired_hold_invoice_ids_query()),
        )
        .order_by(sa.func.coalesce(Invoice.issued_at, Invoice.created_at).desc(), Invoice.id.desc())
        .limit(100)
    ).all()
    payable_invoices = [_billing_invoice_item(session, invoice, tenant, currency, now) for invoice, tenant in payable_invoice_rows]

    submitted_rows = session.execute(
        select(Invoice, Tenant)
        .join(Tenant, Tenant.id == Invoice.tenant_id)
        .where(Invoice.status == "submitted")
        .order_by(Invoice.created_at.asc(), Invoice.id.asc())
        .limit(100)
    ).all()
    submitted_invoices = [_billing_invoice_item(session, invoice, tenant, currency, now) for invoice, tenant in submitted_rows]

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
