from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HostelProfile, Invoice, Payment, Receipt, ReceiptEvent, Tenant, User
from app.notifications.providers import EmailProvider, SmsProvider, WhatsAppProvider
from app.receipts import build_receipt_pdf
from app.services.common import format_money, get_base_currency
from app.services.invoicing import get_paid_total
from app.services.lifecycle import format_timestamp
from app.services.receipt_security import (
    build_receipt_verification_code,
    build_receipt_verification_url,
    mask_phone_number,
    verify_receipt_verification_code,
)
from app.services.settings import get_or_create_notification_settings, notification_settings_map
from ...deps import get_current_user, get_db_session
from ...schemas import (
    ActionResponse,
    BillingInvoiceItem,
    BillingReceiptItem,
    PaymentSummary,
    ReceiptDetailResponse,
    ReceiptVerificationResponse,
    TenantListItem,
)

router = APIRouter()


def _billing_invoice_item(session: Session, invoice: Invoice, tenant: Tenant, currency: str) -> BillingInvoiceItem:
    paid_total = Decimal(str(get_paid_total(session, int(invoice.id))))
    total = Decimal(str(invoice.total or 0))
    balance = total - paid_total
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
    )


def _get_receipt_bundle(session: Session, receipt_id: int) -> tuple[Receipt, Tenant, Payment | None, Invoice | None]:
    bundle = session.execute(
        select(Receipt, Tenant, Payment, Invoice)
        .join(Tenant, Tenant.id == Receipt.tenant_id)
        .outerjoin(Payment, Payment.id == Receipt.payment_id)
        .outerjoin(Invoice, Invoice.id == Payment.invoice_id)
        .where(Receipt.id == receipt_id)
    ).first()
    if bundle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found.")
    return bundle


def _receipt_issued_at_text(receipt: Receipt) -> str:
    return format_timestamp(receipt.issued_at or receipt.created_at) or ""


def _receipt_security_fields(receipt: Receipt) -> tuple[str, str]:
    verification_code = build_receipt_verification_code(
        receipt_no=receipt.receipt_no,
        amount=receipt.amount,
        issued_at=_receipt_issued_at_text(receipt),
    )
    verification_url = build_receipt_verification_url(
        receipt_no=receipt.receipt_no,
        code=verification_code,
    )
    return verification_code, verification_url


@router.get("/verify", response_model=ReceiptVerificationResponse)
def verify_receipt(
    receipt_no: str = Query(min_length=1),
    code: str = Query(min_length=4),
    session: Session = Depends(get_db_session),
) -> ReceiptVerificationResponse:
    bundle = session.execute(
        select(Receipt, Tenant, Payment, Invoice)
        .join(Tenant, Tenant.id == Receipt.tenant_id)
        .outerjoin(Payment, Payment.id == Receipt.payment_id)
        .outerjoin(Invoice, Invoice.id == Payment.invoice_id)
        .where(sa.func.lower(Receipt.receipt_no) == receipt_no.strip().lower())
        .limit(1)
    ).first()
    if bundle is None:
        return ReceiptVerificationResponse(valid=False)

    receipt, tenant, payment, invoice = bundle
    issued_at_text = _receipt_issued_at_text(receipt)
    if not verify_receipt_verification_code(
        receipt_no=receipt.receipt_no,
        amount=receipt.amount,
        issued_at=issued_at_text,
        code=code,
    ):
        return ReceiptVerificationResponse(valid=False)

    return ReceiptVerificationResponse(
        valid=True,
        receipt_no=receipt.receipt_no,
        amount=format_money(receipt.amount, receipt.currency),
        issued_at=issued_at_text,
        tenant_name=tenant.name,
        payment_no=payment.payment_no if payment is not None else None,
        invoice_no=invoice.invoice_no if invoice is not None else None,
    )


@router.get("/{receipt_id}", response_model=ReceiptDetailResponse)
def get_receipt_detail(
    receipt_id: int,
    _user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ReceiptDetailResponse:
    currency = get_base_currency()
    receipt, tenant, payment, invoice = _get_receipt_bundle(session, receipt_id)

    paid_before = None
    balance_after = None
    if payment is not None and invoice is not None:
        total_paid = Decimal(str(get_paid_total(session, int(invoice.id))))
        current_amount = Decimal(str(payment.amount or 0))
        paid_before = format_money(total_paid - current_amount, payment.currency)
        balance_after = format_money(Decimal(str(invoice.total or 0)) - total_paid, payment.currency)

    actor_name = None
    if payment is not None and payment.handled_by_user_id is not None:
        actor = session.get(User, payment.handled_by_user_id)
        if actor is not None:
            actor_name = actor.full_name
    verification_code, verification_url = _receipt_security_fields(receipt)
    provider_settings = notification_settings_map(get_or_create_notification_settings(session))
    sms_provider = SmsProvider(provider_settings)
    email_provider = EmailProvider(provider_settings)
    whatsapp_provider = WhatsAppProvider(provider_settings)
    sms_available = bool(
        (tenant.normalized_phone or tenant.phone)
        and (sms_provider.is_configured() or bool(getattr(sms_provider, "force_mock", False)))
    )
    email_available = bool(
        tenant.email
        and (email_provider.is_configured() or bool(getattr(email_provider, "force_mock", False)))
    )
    whatsapp_available = bool(
        (tenant.normalized_phone or tenant.phone)
        and (whatsapp_provider.is_configured() or bool(getattr(whatsapp_provider, "force_mock", False)))
    )

    receipt_item = BillingReceiptItem(
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

    return ReceiptDetailResponse(
        receipt=receipt_item,
        tenant=TenantListItem(
            id=int(tenant.id),
            name=tenant.name,
            email=tenant.email,
            phone=tenant.phone,
            status=tenant.status,
        ),
        payment=(
            PaymentSummary(
                id=int(payment.id),
                payment_no=payment.payment_no,
                amount=format_money(payment.amount, payment.currency),
                method=payment.method,
                reference=payment.reference,
                status=payment.status,
                paid_at=format_timestamp(payment.paid_at or payment.created_at),
            )
            if payment is not None
            else None
        ),
        invoice=_billing_invoice_item(session, invoice, tenant, currency) if invoice is not None else None,
        paid_before=paid_before,
        balance_after=balance_after,
        received_by=actor_name,
        verification_code=verification_code,
        verification_url=verification_url,
        sms_available=sms_available,
        sms_recipient=mask_phone_number(tenant.normalized_phone or tenant.phone),
        email_available=email_available,
        email_recipient=tenant.email,
        whatsapp_available=whatsapp_available,
        whatsapp_recipient=mask_phone_number(tenant.normalized_phone or tenant.phone),
    )


@router.post("/{receipt_id}/print", response_model=ActionResponse)
def mark_receipt_printed(
    receipt_id: int,
    session: Session = Depends(get_db_session),
    user: dict = Depends(get_current_user),
) -> ActionResponse:
    receipt = session.get(Receipt, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found.")
    receipt.printed_count = int(receipt.printed_count or 0) + 1
    session.add(
        ReceiptEvent(
            receipt_id=int(receipt.id),
            event_type="printed",
            payload={"user_id": int(user["id"]), "at": datetime.now(timezone.utc).isoformat()},
        )
    )
    session.commit()
    return ActionResponse(
        message="Receipt marked as printed.",
        receipt_id=int(receipt.id),
    )


@router.post("/{receipt_id}/send-sms", response_model=ActionResponse)
def send_receipt_sms(
    receipt_id: int,
    session: Session = Depends(get_db_session),
    user: dict = Depends(get_current_user),
) -> ActionResponse:
    receipt, tenant, payment, invoice = _get_receipt_bundle(session, receipt_id)
    recipient = (tenant.normalized_phone or tenant.phone or "").strip()
    if not recipient:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant does not have a phone number.")

    settings = get_or_create_notification_settings(session)
    provider = SmsProvider(notification_settings_map(settings))
    if not provider.is_configured() and not bool(getattr(provider, "force_mock", False)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SMS provider is not configured.")

    verification_code, verification_url = _receipt_security_fields(receipt)
    issued_at_text = _receipt_issued_at_text(receipt)
    message_lines = [
        f"Receipt {receipt.receipt_no}",
        f"Amount: {format_money(receipt.amount, receipt.currency)}",
        f"Issued: {issued_at_text}",
    ]
    if tenant.name:
        message_lines.insert(0, f"{tenant.name}, payment received.")
    if payment is not None and payment.payment_no:
        message_lines.append(f"Payment: {payment.payment_no}")
    if invoice is not None and invoice.invoice_no:
        message_lines.append(f"Invoice: {invoice.invoice_no}")
    message_lines.append(f"Verify: {verification_code}")
    message_lines.append(verification_url)

    result = provider.send_message(recipient, "\n".join(message_lines))
    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.error or "SMS delivery failed.",
        )

    session.add(
        ReceiptEvent(
            receipt_id=int(receipt.id),
            event_type="sms_sent",
            payload={
                "user_id": int(user["id"]),
                "recipient": recipient,
                "provider_id": result.provider_id,
                "at": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    session.commit()
    return ActionResponse(
        message="Receipt SMS sent.",
        receipt_id=int(receipt.id),
    )


@router.post("/{receipt_id}/send-email", response_model=ActionResponse)
def send_receipt_email(
    receipt_id: int,
    session: Session = Depends(get_db_session),
    user: dict = Depends(get_current_user),
) -> ActionResponse:
    receipt, tenant, payment, invoice = _get_receipt_bundle(session, receipt_id)
    recipient = (tenant.email or "").strip()
    if not recipient:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant does not have an email address.")
    settings = get_or_create_notification_settings(session)
    provider = EmailProvider(notification_settings_map(settings))
    if not provider.is_configured() and not bool(getattr(provider, "force_mock", False)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email provider is not configured.")

    verification_code, verification_url = _receipt_security_fields(receipt)
    body_lines = [
        f"Receipt {receipt.receipt_no}",
        f"Amount: {format_money(receipt.amount, receipt.currency)}",
        f"Issued: {_receipt_issued_at_text(receipt)}",
    ]
    if payment is not None and payment.payment_no:
        body_lines.append(f"Payment: {payment.payment_no}")
    if invoice is not None and invoice.invoice_no:
        body_lines.append(f"Invoice: {invoice.invoice_no}")
    body_lines.append(f"Verify code: {verification_code}")
    body_lines.append(verification_url)
    result = provider.send_message(
        to=recipient,
        subject=f"Receipt {receipt.receipt_no}",
        body="\n".join(body_lines),
    )
    if not result.ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error or "Email delivery failed.")
    session.add(
        ReceiptEvent(
            receipt_id=int(receipt.id),
            event_type="email_sent",
            payload={
                "user_id": int(user["id"]),
                "recipient": recipient,
                "provider_id": result.provider_id,
                "at": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    session.commit()
    return ActionResponse(message="Receipt email sent.", receipt_id=int(receipt.id))


@router.post("/{receipt_id}/send-whatsapp", response_model=ActionResponse)
def send_receipt_whatsapp(
    receipt_id: int,
    session: Session = Depends(get_db_session),
    user: dict = Depends(get_current_user),
) -> ActionResponse:
    receipt, tenant, payment, invoice = _get_receipt_bundle(session, receipt_id)
    recipient = (tenant.normalized_phone or tenant.phone or "").strip()
    if not recipient:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant does not have a phone number.")
    settings = get_or_create_notification_settings(session)
    provider = WhatsAppProvider(notification_settings_map(settings))
    if not provider.is_configured() and not bool(getattr(provider, "force_mock", False)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="WhatsApp provider is not configured.")

    verification_code, verification_url = _receipt_security_fields(receipt)
    message_lines = [
        f"Receipt {receipt.receipt_no}",
        f"Amount: {format_money(receipt.amount, receipt.currency)}",
        f"Issued: {_receipt_issued_at_text(receipt)}",
        f"Verify code: {verification_code}",
        verification_url,
    ]
    if payment is not None and payment.payment_no:
        message_lines.insert(2, f"Payment: {payment.payment_no}")
    if invoice is not None and invoice.invoice_no:
        message_lines.insert(3, f"Invoice: {invoice.invoice_no}")
    result = provider.send_message(recipient, "\n".join(message_lines))
    if not result.ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error or "WhatsApp delivery failed.")
    session.add(
        ReceiptEvent(
            receipt_id=int(receipt.id),
            event_type="whatsapp_sent",
            payload={
                "user_id": int(user["id"]),
                "recipient": recipient,
                "provider_id": result.provider_id,
                "at": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    session.commit()
    return ActionResponse(message="Receipt WhatsApp sent.", receipt_id=int(receipt.id))


@router.get("/{receipt_id}/pdf")
def download_receipt_pdf(
    receipt_id: int,
    _user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> Response:
    receipt, tenant, payment, invoice = _get_receipt_bundle(session, receipt_id)
    if payment is None or invoice is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Receipt is missing payment or invoice context.")

    actor_name = None
    if payment.handled_by_user_id is not None:
        actor = session.get(User, payment.handled_by_user_id)
        if actor is not None:
            actor_name = actor.full_name

    profile = session.execute(select(HostelProfile)).scalars().first()
    total_paid = Decimal(str(get_paid_total(session, int(invoice.id))))
    current_amount = Decimal(str(payment.amount or 0))
    verification_code, verification_url = _receipt_security_fields(receipt)
    pdf_bytes = build_receipt_pdf(
        receipt,
        payment,
        invoice,
        tenant,
        actor_name,
        profile=profile,
        paid_before=str((total_paid - current_amount).quantize(Decimal("0.01"))),
        balance_after=str((Decimal(str(invoice.total or 0)) - total_paid).quantize(Decimal("0.01"))),
        verification_code=verification_code,
        verification_url=verification_url,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{receipt.receipt_no}.pdf"'},
    )
