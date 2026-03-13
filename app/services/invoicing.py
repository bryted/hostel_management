from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, Bed, Invoice, InvoiceItem, Payment, Receipt, Room
from app.services.common import as_decimal
from app.services.reservations import release_reservation_on_payment, reserve_bed_for_invoice


class InvoiceValidationError(ValueError):
    pass


def get_paid_total(session: Session, invoice_id: int) -> Decimal:
    total = session.execute(
        select(sa.func.coalesce(sa.func.sum(Payment.amount), 0)).where(
            Payment.invoice_id == invoice_id,
            Payment.status != "voided",
        )
    ).scalar_one()
    return Decimal(str(total))


def update_invoice_status_after_payment(invoice: Invoice, paid_total: Decimal, now: datetime) -> None:
    if paid_total >= Decimal(str(invoice.total)):
        invoice.status = "paid"
        invoice.paid_at = invoice.paid_at or now
    elif paid_total > Decimal("0"):
        invoice.status = "partially_paid"
        invoice.paid_at = None
    else:
        invoice.status = "approved"
        invoice.paid_at = None


def update_invoice_totals(
    invoice: Invoice,
    subtotal: Decimal,
    tax: Decimal,
    discount: Decimal,
) -> Decimal:
    subtotal = as_decimal(subtotal)
    tax = as_decimal(tax)
    discount = as_decimal(discount)

    if discount < Decimal("0"):
        raise InvoiceValidationError("Discount cannot be negative.")
    if tax < Decimal("0"):
        raise InvoiceValidationError("Tax cannot be negative.")
    if discount > subtotal:
        raise InvoiceValidationError("Discount cannot exceed subtotal.")

    total = subtotal + tax - discount
    if total < Decimal("0"):
        raise InvoiceValidationError("Invoice total cannot be negative.")

    invoice.subtotal = subtotal
    invoice.tax = tax
    invoice.discount = discount
    invoice.total = total
    return total


def _upsert_bed_invoice_item(session: Session, invoice: Invoice, room: Room, bed: Bed) -> None:
    description = f"{room.room_code} {bed.bed_label} - Annual bed fee"
    unit_price = Decimal(str(room.unit_price_per_bed))

    existing = (
        session.execute(
            select(InvoiceItem)
            .where(InvoiceItem.invoice_id == invoice.id)
            .order_by(InvoiceItem.line_no)
        )
        .scalars()
        .first()
    )
    if existing:
        existing.description = description
        existing.quantity = Decimal("1")
        existing.unit_price = unit_price
        existing.amount = unit_price
        return

    session.add(
        InvoiceItem(
            invoice_id=invoice.id,
            line_no=1,
            description=description,
            quantity=1,
            unit_price=unit_price,
            amount=unit_price,
        )
    )


def create_invoice(
    session: Session,
    *,
    tenant_id: int,
    user_id: int,
    reserved_bed_id: int,
    currency: str,
    tax: Decimal,
    discount: Decimal,
    notes: str | None,
    status: str,
    due_at: datetime | None,
    hold_until: datetime | None,
    now: datetime,
) -> Invoice:
    bed = session.get(Bed, reserved_bed_id)
    if bed is None or bed.status != "AVAILABLE":
        raise InvoiceValidationError("Selected bed is no longer available.")

    room = session.get(Room, bed.room_id)
    if room is None:
        raise InvoiceValidationError("Room details not found for selected bed.")

    subtotal = Decimal(str(room.unit_price_per_bed))
    invoice = Invoice(
        tenant_id=tenant_id,
        user_id=user_id,
        status=status,
        currency=currency,
        subtotal=subtotal,
        tax=Decimal("0"),
        discount=Decimal("0"),
        total=subtotal,
        notes=notes,
        due_at=due_at,
        issued_at=now if status in {"submitted", "approved", "partially_paid", "paid"} else None,
        reserved_bed_id=reserved_bed_id,
    )
    update_invoice_totals(invoice, subtotal, as_decimal(tax), as_decimal(discount))
    session.add(invoice)
    session.flush()

    _upsert_bed_invoice_item(session, invoice, room, bed)
    if invoice.status in {"draft", "submitted", "approved", "partially_paid"}:
        if hold_until is None:
            raise InvoiceValidationError("Reservation hold expiry is required for unpaid invoices.")
        reserve_bed_for_invoice(
            session,
            invoice_id=invoice.id,
            tenant_id=tenant_id,
            bed_id=reserved_bed_id,
            hold_until=hold_until,
            user_id=user_id,
            now=now,
        )
    return invoice


def record_payment(
    session: Session,
    *,
    invoice: Invoice,
    user_id: int,
    amount: Decimal,
    method: str,
    reference: str | None,
    now: datetime,
) -> tuple[Payment, Receipt, Decimal]:
    amount = as_decimal(amount)
    if amount <= Decimal("0"):
        raise InvoiceValidationError("Payment amount must be greater than zero.")

    conflicting_allocation = session.execute(
        select(Allocation.id).where(
            Allocation.tenant_id == invoice.tenant_id,
            Allocation.status == "CONFIRMED",
            Allocation.invoice_id != invoice.id,
        )
    ).scalar_one_or_none()
    if conflicting_allocation is not None:
        raise InvoiceValidationError(
            "Tenant already has an active bed allocation. End or transfer the current stay before taking payment for another room."
        )

    paid_total = get_paid_total(session, invoice.id)
    balance = Decimal(str(invoice.total)) - paid_total
    if amount > balance:
        raise InvoiceValidationError("Payment amount cannot exceed the remaining balance.")

    payment = Payment(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        handled_by_user_id=user_id,
        amount=amount,
        currency=invoice.currency,
        method=method,
        reference=(reference or "").strip() or None,
        status="completed",
        paid_at=now,
    )
    session.add(payment)
    session.flush()

    receipt = Receipt(
        tenant_id=invoice.tenant_id,
        payment_id=payment.id,
        amount=amount,
        currency=invoice.currency,
        issued_at=now,
    )
    session.add(receipt)
    session.flush()

    updated_paid_total = paid_total + amount
    update_invoice_status_after_payment(invoice, updated_paid_total, now)
    release_reservation_on_payment(
        session,
        invoice_id=invoice.id,
        user_id=user_id,
        now=now,
        reason="Released on payment",
    )

    return payment, receipt, updated_paid_total


def update_invoice_details(
    session: Session,
    *,
    invoice: Invoice,
    user_id: int,
    reserved_bed_id: int,
    tax: Decimal,
    discount: Decimal,
    notes: str | None,
    due_at: datetime | None,
    hold_until: datetime,
    now: datetime,
) -> Invoice:
    if invoice.status not in {"draft", "submitted", "approved", "partially_paid"}:
        raise InvoiceValidationError("Only unpaid invoices can be edited.")
    if get_paid_total(session, int(invoice.id)) > Decimal("0"):
        raise InvoiceValidationError("Invoices with recorded payments cannot be edited.")
    confirmed_allocation = session.execute(
        select(Allocation.id).where(Allocation.invoice_id == invoice.id, Allocation.status == "CONFIRMED")
    ).scalar_one_or_none()
    if confirmed_allocation is not None:
        raise InvoiceValidationError("Allocated invoices cannot be edited.")

    bed = session.get(Bed, reserved_bed_id)
    if bed is None or bed.status == "OCCUPIED":
        raise InvoiceValidationError("Selected bed is not available.")
    if bed.status == "OUT_OF_SERVICE":
        raise InvoiceValidationError("Selected bed is out of service.")

    room = session.get(Room, bed.room_id)
    if room is None:
        raise InvoiceValidationError("Room details not found for selected bed.")

    subtotal = Decimal(str(room.unit_price_per_bed))
    invoice.reserved_bed_id = reserved_bed_id
    invoice.notes = notes
    invoice.due_at = due_at
    if invoice.status in {"submitted", "approved", "partially_paid"} and invoice.issued_at is None:
        invoice.issued_at = now
    update_invoice_totals(invoice, subtotal, as_decimal(tax), as_decimal(discount))
    _upsert_bed_invoice_item(session, invoice, room, bed)
    reserve_bed_for_invoice(
        session,
        invoice_id=int(invoice.id),
        tenant_id=int(invoice.tenant_id),
        bed_id=reserved_bed_id,
        hold_until=hold_until,
        user_id=user_id,
        now=now,
    )
    return invoice


def cancel_invoice(
    session: Session,
    *,
    invoice: Invoice,
    user_id: int,
    reason: str,
    now: datetime,
) -> Invoice:
    if invoice.status in {"paid", "cancelled"}:
        raise InvoiceValidationError("Invoice cannot be cancelled.")
    paid_total = get_paid_total(session, int(invoice.id))
    if paid_total > Decimal("0"):
        raise InvoiceValidationError("Invoice with payments cannot be cancelled.")
    confirmed_allocation = session.execute(
        select(Allocation.id).where(Allocation.invoice_id == invoice.id, Allocation.status == "CONFIRMED")
    ).scalar_one_or_none()
    if confirmed_allocation is not None:
        raise InvoiceValidationError("Invoice has an active allocation.")
    invoice.status = "cancelled"
    release_reservation_on_payment(
        session,
        invoice_id=int(invoice.id),
        user_id=user_id,
        now=now,
        reason=reason.strip() or "Invoice cancelled",
    )
    return invoice


def void_payment(
    session: Session,
    *,
    payment: Payment,
    user_id: int,
    reason: str,
    hold_until: datetime | None,
    now: datetime,
) -> Payment:
    if payment.status == "voided":
        raise InvoiceValidationError("Payment is already voided.")
    invoice = session.get(Invoice, payment.invoice_id) if payment.invoice_id is not None else None
    if invoice is None:
        raise InvoiceValidationError("Payment is not linked to an invoice.")
    confirmed_allocation = session.execute(
        select(Allocation.id).where(Allocation.invoice_id == invoice.id, Allocation.status == "CONFIRMED")
    ).scalar_one_or_none()
    if confirmed_allocation is not None:
        raise InvoiceValidationError("End the active allocation before voiding this payment.")

    payment.status = "voided"
    payment.voided_at = now
    payment.void_reason = reason.strip() or "Payment voided"

    paid_total = get_paid_total(session, int(invoice.id))
    update_invoice_status_after_payment(invoice, paid_total, now)
    if invoice.status in {"approved", "partially_paid", "draft", "submitted"} and invoice.reserved_bed_id and hold_until is not None:
        reserve_bed_for_invoice(
            session,
            invoice_id=int(invoice.id),
            tenant_id=int(invoice.tenant_id),
            bed_id=int(invoice.reserved_bed_id),
            hold_until=hold_until,
            user_id=user_id,
            now=now,
        )
    return payment
