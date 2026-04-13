from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Sequence

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, Bed, Invoice, InvoiceItem, Payment, PaymentAllocation, Receipt, Room, Tenant
from app.services.academic_years import resolve_academic_year
from app.services.common import as_decimal, bed_is_in_operational_inventory
from app.services.reservations import release_reservation_on_payment, reserve_bed_for_invoice


class InvoiceValidationError(ValueError):
    pass


def paid_totals_subquery() -> sa.Subquery:
    return (
        select(
            PaymentAllocation.invoice_id.label("invoice_id"),
            sa.func.coalesce(sa.func.sum(PaymentAllocation.allocated_amount), 0).label("paid_total"),
        )
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(
            Payment.status != "voided",
        )
        .group_by(PaymentAllocation.invoice_id)
        .subquery()
    )


def get_paid_total(session: Session, invoice_id: int) -> Decimal:
    total = session.execute(
        select(sa.func.coalesce(sa.func.sum(PaymentAllocation.allocated_amount), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(
            PaymentAllocation.invoice_id == invoice_id,
            Payment.status != "voided",
        )
    ).scalar_one()
    return Decimal(str(total))


def get_payment_allocated_total(session: Session, payment_id: int) -> Decimal:
    total = session.execute(
        select(sa.func.coalesce(sa.func.sum(PaymentAllocation.allocated_amount), 0)).where(
            PaymentAllocation.payment_id == payment_id
        )
    ).scalar_one()
    return Decimal(str(total or 0))


def get_payment_unallocated_total(session: Session, payment: Payment) -> Decimal:
    return Decimal(str(payment.amount or 0)) - get_payment_allocated_total(session, int(payment.id))


def payment_allocations_for_payment_ids(
    session: Session,
    payment_ids: Sequence[int],
) -> dict[int, list[tuple[PaymentAllocation, Invoice]]]:
    if not payment_ids:
        return {}
    rows = session.execute(
        select(PaymentAllocation, Invoice)
        .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
        .where(PaymentAllocation.payment_id.in_(tuple(int(payment_id) for payment_id in payment_ids)))
        .order_by(PaymentAllocation.payment_id.asc(), PaymentAllocation.allocated_at.asc(), PaymentAllocation.id.asc())
    ).all()
    allocation_map: dict[int, list[tuple[PaymentAllocation, Invoice]]] = {}
    for allocation, invoice in rows:
        allocation_map.setdefault(int(allocation.payment_id), []).append((allocation, invoice))
    return allocation_map


def payment_invoice_summary_text(
    session: Session,
    payment_id: int,
    *,
    allocation_map: dict[int, list[tuple[PaymentAllocation, Invoice]]] | None = None,
) -> str:
    if allocation_map is None:
        allocation_map = payment_allocations_for_payment_ids(session, [payment_id])
    allocations = allocation_map.get(int(payment_id), [])
    if not allocations:
        return "-"
    if len(allocations) == 1:
        return allocations[0][1].invoice_no
    return f"Multiple ({len(allocations)})"


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
    if not bed_is_in_operational_inventory(session, int(bed.id)):
        raise InvoiceValidationError("Selected bed is in inactive inventory.")

    room = session.get(Room, bed.room_id)
    if room is None:
        raise InvoiceValidationError("Room details not found for selected bed.")

    subtotal = Decimal(str(room.unit_price_per_bed))
    academic_year = resolve_academic_year(session, as_of=due_at or now)
    invoice = Invoice(
        tenant_id=tenant_id,
        user_id=user_id,
        academic_year_id=academic_year.id,
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
    payment, receipt, invoice_totals = record_tenant_payment(
        session,
        tenant_id=int(invoice.tenant_id),
        user_id=user_id,
        amount=amount,
        method=method,
        reference=reference,
        allocations=[{"invoice_id": int(invoice.id), "amount": amount}],
        now=now,
    )
    return payment, receipt, invoice_totals[int(invoice.id)]


def record_tenant_payment(
    session: Session,
    *,
    tenant_id: int,
    user_id: int,
    amount: Decimal,
    method: str,
    reference: str | None,
    allocations: Sequence[dict[str, object]],
    now: datetime,
) -> tuple[Payment, Receipt, dict[int, Decimal]]:
    amount = as_decimal(amount)
    if amount <= Decimal("0"):
        raise InvoiceValidationError("Payment amount must be greater than zero.")
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise InvoiceValidationError("Tenant not found.")

    normalized_allocations: list[tuple[Invoice, Decimal]] = []
    allocation_total = Decimal("0")
    seen_invoice_ids: set[int] = set()
    for raw in allocations:
        invoice_id = int(raw.get("invoice_id") or 0)
        allocated_amount = as_decimal(raw.get("amount") or 0)
        if allocated_amount <= Decimal("0"):
            continue
        invoice = session.get(Invoice, invoice_id)
        if invoice is None:
            raise InvoiceValidationError("Invoice not found for allocation.")
        if int(invoice.tenant_id) != int(tenant_id):
            raise InvoiceValidationError("Payments can only be allocated to invoices for the selected tenant.")
        if invoice.status not in {"approved", "partially_paid"}:
            raise InvoiceValidationError("Payments can only be allocated to approved or partially paid invoices.")
        if invoice_id in seen_invoice_ids:
            raise InvoiceValidationError("Duplicate invoice allocation detected in one payment.")
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
        paid_total = get_paid_total(session, int(invoice.id))
        balance = Decimal(str(invoice.total)) - paid_total
        if allocated_amount > balance:
            raise InvoiceValidationError(f"Allocated amount exceeds the remaining balance for {invoice.invoice_no}.")
        seen_invoice_ids.add(invoice_id)
        allocation_total += allocated_amount
        normalized_allocations.append((invoice, allocated_amount))

    if allocation_total > amount:
        raise InvoiceValidationError("Allocated amounts cannot exceed the payment amount.")

    academic_year = None
    for invoice, _allocated_amount in normalized_allocations:
        academic_year = academic_year or invoice.academic_year
    academic_year = academic_year or resolve_academic_year(session, as_of=now)
    primary_invoice_id = int(normalized_allocations[0][0].id) if normalized_allocations else None
    payment = Payment(
        tenant_id=tenant_id,
        invoice_id=primary_invoice_id,
        academic_year_id=academic_year.id,
        handled_by_user_id=user_id,
        amount=amount,
        currency=normalized_allocations[0][0].currency if normalized_allocations else "GHS",
        method=method,
        reference=(reference or "").strip() or None,
        status="completed",
        paid_at=now,
    )
    session.add(payment)
    session.flush()

    receipt = Receipt(
        tenant_id=tenant_id,
        payment_id=payment.id,
        academic_year_id=payment.academic_year_id,
        amount=amount,
        currency=payment.currency,
        issued_at=now,
    )
    session.add(receipt)
    session.flush()

    updated_invoice_totals: dict[int, Decimal] = {}
    for invoice, allocated_amount in normalized_allocations:
        current_paid_total = get_paid_total(session, int(invoice.id))
        session.add(
            PaymentAllocation(
                payment_id=payment.id,
                invoice_id=invoice.id,
                tenant_id=tenant_id,
                academic_year_id=invoice.academic_year_id or payment.academic_year_id,
                allocated_amount=allocated_amount,
                allocated_at=now,
                allocated_by_user_id=user_id,
            )
        )
        updated_paid_total = current_paid_total + allocated_amount
        update_invoice_status_after_payment(invoice, updated_paid_total, now)
        release_reservation_on_payment(
            session,
            invoice_id=int(invoice.id),
            user_id=user_id,
            now=now,
            reason="Released on payment",
        )
        updated_invoice_totals[int(invoice.id)] = updated_paid_total

    return payment, receipt, updated_invoice_totals


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
    if not bed_is_in_operational_inventory(session, int(bed.id)):
        raise InvoiceValidationError("Selected bed is in inactive inventory.")

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
    allocation_rows = session.execute(
        select(PaymentAllocation, Invoice)
        .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
        .where(PaymentAllocation.payment_id == payment.id)
    ).all()
    invoices = [invoice for _allocation, invoice in allocation_rows]
    if not invoices:
        raise InvoiceValidationError("Payment is not linked to any invoice allocation.")
    for invoice in invoices:
        confirmed_allocation = session.execute(
            select(Allocation.id).where(Allocation.invoice_id == invoice.id, Allocation.status == "CONFIRMED")
        ).scalar_one_or_none()
        if confirmed_allocation is not None:
            raise InvoiceValidationError("End the active allocation before voiding this payment.")

    payment.status = "voided"
    payment.voided_at = now
    payment.void_reason = reason.strip() or "Payment voided"

    for invoice in invoices:
        paid_total = get_paid_total(session, int(invoice.id))
        update_invoice_status_after_payment(invoice, paid_total, now)
        if (
            invoice.status in {"approved", "partially_paid", "draft", "submitted"}
            and invoice.reserved_bed_id
            and hold_until is not None
        ):
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
