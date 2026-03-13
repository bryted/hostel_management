from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Allocation,
    AllocationEvent,
    Bed,
    BedEvent,
    BedReservation,
    Invoice,
    InvoiceEvent,
    Payment,
    Receipt,
    Tenant,
    TenantEvent,
)
from app.services.common import format_money


def _log_invoice_event(session: Session, invoice_id: int, event_type: str, payload: dict[str, Any]) -> None:
    session.add(InvoiceEvent(invoice_id=invoice_id, event_type=event_type, payload=payload))


def _log_tenant_event(
    session: Session,
    tenant_id: int,
    event_type: str,
    user_id: int | None,
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(TenantEvent(tenant_id=tenant_id, event_type=event_type, user_id=user_id, detail_json=detail))


def _log_bed_event(
    session: Session,
    bed_id: int,
    event_type: str,
    user_id: int | None,
    invoice_id: int | None = None,
    tenant_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        BedEvent(
            bed_id=bed_id,
            event_type=event_type,
            user_id=user_id,
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            detail_json=detail,
        )
    )


def _log_allocation_event(
    session: Session,
    allocation_id: int,
    event_type: str,
    user_id: int | None,
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        AllocationEvent(
            allocation_id=allocation_id,
            event_type=event_type,
            user_id=user_id,
            detail_json=detail,
        )
    )


def summarize_detail(detail: dict[str, Any] | None) -> str:
    if not detail:
        return ""
    parts: list[str] = []
    for key, value in detail.items():
        if value in (None, ""):
            continue
        parts.append(f"{str(key).replace('_', ' ')}: {value}")
    return " | ".join(parts)


def format_timestamp(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def extend_reservation_hold(
    session: Session,
    *,
    reservation_id: int,
    extra_hours: int,
    user_id: int,
    reason: str,
    now: datetime,
) -> BedReservation:
    reservation = session.get(BedReservation, reservation_id)
    if reservation is None or reservation.status != "ACTIVE":
        raise ValueError("Reservation is not active.")
    reservation.expires_at = (reservation.expires_at or now) + timedelta(hours=int(extra_hours))
    reservation.extended_at = now
    reservation.extended_by = user_id
    reservation.extension_reason = reason.strip() or None
    reservation.extension_count = int(reservation.extension_count or 0) + 1
    bed = session.get(Bed, reservation.bed_id)
    if bed is not None and bed.status != "OUT_OF_SERVICE":
        bed.status = "RESERVED"
    expires_at = reservation.expires_at
    detail = {
        "reservation_id": reservation.id,
        "extra_hours": int(extra_hours),
        "expires_at": expires_at.isoformat() if isinstance(expires_at, datetime) else "",
        "reason": reason.strip() or "",
    }
    _log_bed_event(session, reservation.bed_id, "RESERVATION_EXTENDED", user_id, reservation.invoice_id, reservation.tenant_id, detail)
    if reservation.invoice_id:
        _log_invoice_event(session, reservation.invoice_id, "reservation_extended", detail)
    _log_tenant_event(session, reservation.tenant_id, "RESERVATION_EXTENDED", user_id, detail)
    return reservation


def cancel_reservation_hold(
    session: Session,
    *,
    reservation_id: int,
    user_id: int,
    reason: str,
    now: datetime,
) -> BedReservation:
    reservation = session.get(BedReservation, reservation_id)
    if reservation is None or reservation.status != "ACTIVE":
        raise ValueError("Reservation is not active.")
    reservation.status = "CANCELLED"
    reservation.cancelled_at = now
    reservation.cancelled_by = user_id
    reservation.cancel_reason = reason.strip() or "Cancelled from workspace"
    bed = session.get(Bed, reservation.bed_id)
    if bed is not None and bed.status == "RESERVED":
        active_allocation = session.execute(
            select(Allocation.id).where(Allocation.bed_id == bed.id, Allocation.status == "CONFIRMED")
        ).scalar_one_or_none()
        if active_allocation is None:
            bed.status = "AVAILABLE"
    detail = {"reservation_id": reservation.id, "reason": reservation.cancel_reason}
    _log_bed_event(session, reservation.bed_id, "RESERVATION_CANCELLED", user_id, reservation.invoice_id, reservation.tenant_id, detail)
    if reservation.invoice_id:
        _log_invoice_event(session, reservation.invoice_id, "reservation_cancelled", detail)
    _log_tenant_event(session, reservation.tenant_id, "RESERVATION_CANCELLED", user_id, detail)
    return reservation


def end_allocation_stay(
    session: Session,
    *,
    allocation_id: int,
    user_id: int,
    now: datetime,
    reason: str,
) -> Allocation:
    allocation = session.get(Allocation, allocation_id)
    if allocation is None or allocation.status != "CONFIRMED":
        raise ValueError("Allocation is not active.")
    allocation.status = "ENDED"
    allocation.end_date = now
    allocation.ended_at = now
    allocation.ended_by = user_id
    allocation.ended_reason = reason.strip() or "Move-out completed"
    bed = session.get(Bed, allocation.bed_id)
    if bed is not None and bed.status == "OCCUPIED":
        bed.status = "AVAILABLE"
    detail = {
        "allocation_id": allocation.id,
        "bed_id": allocation.bed_id,
        "invoice_id": allocation.invoice_id,
        "reason": allocation.ended_reason,
        "at": now.isoformat(),
    }
    _log_allocation_event(session, allocation.id, "ALLOCATION_ENDED", user_id, detail)
    _log_bed_event(session, allocation.bed_id, "ALLOCATION_ENDED", user_id, allocation.invoice_id, allocation.tenant_id, detail)
    if allocation.invoice_id:
        _log_invoice_event(session, allocation.invoice_id, "allocation_ended", detail)
    _log_tenant_event(session, allocation.tenant_id, "TENANT_MOVED_OUT", user_id, detail)
    active_other_allocations = session.execute(
        select(sa.func.count(Allocation.id)).where(Allocation.tenant_id == allocation.tenant_id, Allocation.status == "CONFIRMED")
    ).scalar_one()
    tenant = session.get(Tenant, allocation.tenant_id)
    if tenant is not None and int(active_other_allocations or 0) == 0:
        tenant.status = "inactive"
    return allocation


def transfer_allocation_bed(
    session: Session,
    *,
    allocation_id: int,
    new_bed_id: int,
    user_id: int,
    now: datetime,
    reason: str,
) -> Allocation:
    allocation = session.get(Allocation, allocation_id)
    if allocation is None or allocation.status != "CONFIRMED":
        raise ValueError("Allocation is not active.")
    if int(allocation.bed_id) == int(new_bed_id):
        raise ValueError("Select a different bed.")
    new_bed = session.get(Bed, new_bed_id)
    if new_bed is None:
        raise ValueError("Target bed not found.")
    if new_bed.status in {"OUT_OF_SERVICE", "OCCUPIED"}:
        raise ValueError("Target bed is not available for transfer.")
    conflicting_allocation = session.execute(
        select(Allocation.id).where(Allocation.bed_id == new_bed.id, Allocation.status == "CONFIRMED")
    ).scalar_one_or_none()
    if conflicting_allocation is not None:
        raise ValueError("Target bed already has an active allocation.")
    conflicting_reservation = session.execute(
        select(BedReservation.id).where(
            BedReservation.bed_id == new_bed.id,
            BedReservation.status == "ACTIVE",
            sa.or_(BedReservation.invoice_id.is_(None), BedReservation.invoice_id != allocation.invoice_id),
        )
    ).scalar_one_or_none()
    if conflicting_reservation is not None:
        raise ValueError("Target bed has an active reservation.")

    old_bed_id = int(allocation.bed_id)
    old_bed = session.get(Bed, old_bed_id)
    allocation.status = "ENDED"
    allocation.end_date = now
    allocation.ended_at = now
    allocation.ended_by = user_id
    allocation.ended_reason = f"Transferred: {reason.strip() or 'bed change'}"
    if old_bed is not None and old_bed.status == "OCCUPIED":
        old_bed.status = "AVAILABLE"
    new_allocation = Allocation(
        bed_id=new_bed.id,
        tenant_id=allocation.tenant_id,
        invoice_id=allocation.invoice_id,
        status="CONFIRMED",
        start_date=now,
    )
    session.add(new_allocation)
    session.flush()
    new_bed.status = "OCCUPIED"
    if allocation.invoice_id:
        invoice = session.get(Invoice, allocation.invoice_id)
        if invoice is not None:
            invoice.reserved_bed_id = new_bed.id
        active_reservations = session.execute(
            select(BedReservation).where(BedReservation.invoice_id == allocation.invoice_id, BedReservation.status == "ACTIVE")
        ).scalars().all()
        for reservation in active_reservations:
            reservation.status = "CANCELLED"
            reservation.cancelled_at = now
            reservation.cancelled_by = user_id
            reservation.cancel_reason = "Allocation transferred"
    detail = {
        "old_bed_id": old_bed_id,
        "new_bed_id": int(new_bed.id),
        "invoice_id": allocation.invoice_id,
        "reason": reason.strip() or "bed change",
        "at": now.isoformat(),
    }
    _log_allocation_event(session, allocation.id, "ALLOCATION_TRANSFERRED_OUT", user_id, detail)
    _log_allocation_event(session, new_allocation.id, "ALLOCATION_TRANSFERRED_IN", user_id, detail)
    _log_bed_event(session, old_bed_id, "BED_TRANSFERRED_OUT", user_id, allocation.invoice_id, allocation.tenant_id, detail)
    _log_bed_event(session, new_bed.id, "BED_TRANSFERRED_IN", user_id, allocation.invoice_id, allocation.tenant_id, detail)
    if allocation.invoice_id:
        _log_invoice_event(session, allocation.invoice_id, "allocation_transferred", detail)
    _log_tenant_event(session, allocation.tenant_id, "TENANT_TRANSFERRED_BED", user_id, detail)
    return new_allocation


def set_bed_maintenance_status(
    session: Session,
    *,
    bed_id: int,
    user_id: int,
    now: datetime,
    out_of_service: bool,
    reason: str,
) -> Bed:
    bed = session.get(Bed, bed_id)
    if bed is None:
        raise ValueError("Bed not found.")
    if out_of_service:
        active_allocation = session.execute(
            select(Allocation.id).where(Allocation.bed_id == bed.id, Allocation.status == "CONFIRMED")
        ).scalar_one_or_none()
        active_reservation = session.execute(
            select(BedReservation.id).where(BedReservation.bed_id == bed.id, BedReservation.status == "ACTIVE")
        ).scalar_one_or_none()
        if active_allocation is not None:
            raise ValueError("End or transfer the active allocation before blocking this bed.")
        if active_reservation is not None:
            raise ValueError("Cancel the active reservation before blocking this bed.")
        bed.status = "OUT_OF_SERVICE"
        event_type = "BED_OUT_OF_SERVICE"
    else:
        if bed.status != "OUT_OF_SERVICE":
            raise ValueError("Bed is not currently out of service.")
        bed.status = "AVAILABLE"
        event_type = "BED_RETURNED_TO_SERVICE"
    detail = {"bed_id": bed.id, "reason": reason.strip() or "", "at": now.isoformat()}
    _log_bed_event(session, bed.id, event_type, user_id, None, None, detail)
    return bed


def get_tenant_timeline_rows(session: Session, tenant_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    tenant_events = session.execute(
        select(TenantEvent).where(TenantEvent.tenant_id == tenant_id).order_by(TenantEvent.event_at.desc()).limit(20)
    ).scalars().all()
    for event in tenant_events:
        rows.append({"When": event.event_at, "Source": "Tenant", "Event": event.event_type, "Detail": summarize_detail(event.detail_json)})

    invoice_ids = session.execute(select(Invoice.id).where(Invoice.tenant_id == tenant_id)).scalars().all()
    if invoice_ids:
        invoice_events = session.execute(
            select(InvoiceEvent).where(InvoiceEvent.invoice_id.in_(invoice_ids)).order_by(InvoiceEvent.event_at.desc()).limit(20)
        ).scalars().all()
        for event in invoice_events:
            rows.append({"When": event.event_at, "Source": "Invoice", "Event": event.event_type, "Detail": summarize_detail(event.payload)})

        allocation_events = session.execute(
            select(AllocationEvent, Allocation)
            .join(Allocation, Allocation.id == AllocationEvent.allocation_id)
            .where(Allocation.tenant_id == tenant_id)
            .order_by(AllocationEvent.created_at.desc())
            .limit(20)
        ).all()
        for event, allocation in allocation_events:
            detail = dict(event.detail_json or {})
            detail.setdefault("allocation_id", allocation.id)
            rows.append({"When": event.created_at, "Source": "Allocation", "Event": event.event_type, "Detail": summarize_detail(detail)})

    bed_events = session.execute(
        select(BedEvent).where(BedEvent.tenant_id == tenant_id).order_by(BedEvent.created_at.desc()).limit(20)
    ).scalars().all()
    for event in bed_events:
        rows.append({"When": event.created_at, "Source": "Bed", "Event": event.event_type, "Detail": summarize_detail(event.detail_json)})

    payments = session.execute(
        select(Payment).where(Payment.tenant_id == tenant_id).order_by(sa.func.coalesce(Payment.paid_at, Payment.created_at).desc()).limit(20)
    ).scalars().all()
    for payment in payments:
        rows.append(
            {
                "When": payment.paid_at or payment.created_at,
                "Source": "Payment",
                "Event": payment.payment_no,
                "Detail": summarize_detail(
                    {
                        "amount": format_money(payment.amount, payment.currency),
                        "method": payment.method or "",
                        "reference": payment.reference or "",
                        "status": payment.status,
                    }
                ),
            }
        )

    receipts = session.execute(
        select(Receipt).where(Receipt.tenant_id == tenant_id).order_by(sa.func.coalesce(Receipt.issued_at, Receipt.created_at).desc()).limit(20)
    ).scalars().all()
    for receipt in receipts:
        rows.append(
            {
                "When": receipt.issued_at or receipt.created_at,
                "Source": "Receipt",
                "Event": receipt.receipt_no,
                "Detail": summarize_detail({"amount": format_money(receipt.amount, receipt.currency), "printed": int(receipt.printed_count or 0)}),
            }
        )

    rows.sort(key=lambda item: item["When"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return [{"When": format_timestamp(row["When"]), "Source": row["Source"], "Event": row["Event"], "Detail": row["Detail"]} for row in rows[:40]]
