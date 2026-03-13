from __future__ import annotations

from datetime import datetime
import math

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, Bed, BedEvent, BedReservation, Invoice

UNPAID_INVOICE_STATUSES = {"draft", "submitted", "approved", "partially_paid"}


def _has_confirmed_allocation(session: Session, bed_id: int) -> bool:
    allocation_id = session.execute(
        select(Allocation.id)
        .where(Allocation.bed_id == bed_id, Allocation.status == "CONFIRMED")
        .limit(1)
    ).scalar_one_or_none()
    return allocation_id is not None


def _log_bed_event(
    session: Session,
    *,
    bed_id: int,
    event_type: str,
    user_id: int | None,
    invoice_id: int | None,
    tenant_id: int | None,
    detail: dict[str, object] | None = None,
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


def invoice_hold_expired(session: Session, invoice_id: int) -> bool:
    active_reservation = session.execute(
        select(BedReservation.id)
        .where(BedReservation.invoice_id == invoice_id, BedReservation.status == "ACTIVE")
        .limit(1)
    ).scalar_one_or_none()
    if active_reservation is not None:
        return False

    expired_reservation = session.execute(
        select(BedReservation.id)
        .where(BedReservation.invoice_id == invoice_id, BedReservation.status == "EXPIRED")
        .limit(1)
    ).scalar_one_or_none()
    if expired_reservation is None:
        return False

    invoice = session.get(Invoice, invoice_id)
    return invoice is not None and invoice.reserved_bed_id is None


def expired_hold_invoice_ids_query() -> sa.Select:
    return (
        select(BedReservation.invoice_id)
        .join(Invoice, Invoice.id == BedReservation.invoice_id)
        .where(
            BedReservation.invoice_id.is_not(None),
            BedReservation.status == "EXPIRED",
            Invoice.reserved_bed_id.is_(None),
        )
        .group_by(BedReservation.invoice_id)
    )


def invoice_hold_snapshot(
    session: Session,
    invoice_id: int,
    *,
    now: datetime,
) -> tuple[datetime | None, int | None, bool]:
    active_reservation = session.execute(
        select(BedReservation.expires_at)
        .where(BedReservation.invoice_id == invoice_id, BedReservation.status == "ACTIVE")
        .limit(1)
    ).scalar_one_or_none()
    if active_reservation is not None:
        if active_reservation.tzinfo is None:
            active_reservation = active_reservation.replace(tzinfo=now.tzinfo)
        hours_left = max(math.ceil((active_reservation - now).total_seconds() / 3600), 0)
        return active_reservation, hours_left, False
    return None, None, invoice_hold_expired(session, invoice_id)


def reserve_bed_for_invoice(
    session: Session,
    *,
    invoice_id: int,
    tenant_id: int,
    bed_id: int,
    hold_until: datetime,
    user_id: int | None,
    now: datetime,
) -> BedReservation:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise ValueError("Invoice not found for reservation.")
    if invoice.status not in UNPAID_INVOICE_STATUSES:
        raise ValueError("Reservation can only be created for unpaid invoices.")

    bed = session.get(Bed, bed_id)
    if bed is None:
        raise ValueError("Bed not found.")
    if bed.status == "OUT_OF_SERVICE":
        raise ValueError("Bed is out of service.")
    if bed.status == "OCCUPIED":
        raise ValueError("Bed is already occupied.")
    if bed.status not in {"AVAILABLE", "RESERVED"}:
        raise ValueError("Bed is not available for reservation.")
    if _has_confirmed_allocation(session, bed.id):
        raise ValueError("Bed is already allocated.")

    existing_tenant_allocation = session.execute(
        select(Allocation.id).where(
            Allocation.tenant_id == tenant_id,
            Allocation.status == "CONFIRMED",
        )
    ).scalar_one_or_none()
    if existing_tenant_allocation is not None:
        raise ValueError(
            "Tenant already has a confirmed allocation. End or transfer the current stay before reserving another bed."
        )

    existing_tenant_reservation = session.execute(
        select(BedReservation.id)
        .where(
            BedReservation.tenant_id == tenant_id,
            BedReservation.status == "ACTIVE",
            sa.or_(BedReservation.invoice_id.is_(None), BedReservation.invoice_id != invoice_id),
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing_tenant_reservation is not None:
        raise ValueError(
            "Tenant already has an active reservation. Cancel or convert it before reserving another bed."
        )

    # Ensure a single active reservation exists per invoice by cancelling stale ones.
    active_for_invoice = (
        session.execute(
            select(BedReservation)
            .where(BedReservation.invoice_id == invoice_id, BedReservation.status == "ACTIVE")
            .with_for_update()
        )
        .scalars()
        .all()
    )
    for existing in active_for_invoice:
        if existing.bed_id == bed_id:
            existing.expires_at = hold_until
            existing.extended_at = now
            existing.extended_by = user_id
            existing.extension_count = int(existing.extension_count or 0) + 1
            _log_bed_event(
                session,
                bed_id=bed_id,
                event_type="RESERVATION_EXTENDED",
                user_id=user_id,
                invoice_id=invoice_id,
                tenant_id=tenant_id,
                detail={"reservation_id": existing.id, "expires_at": hold_until.isoformat()},
            )
            bed.status = "RESERVED"
            return existing

        existing.status = "CANCELLED"
        existing.cancelled_at = now
        existing.cancelled_by = user_id
        existing.cancel_reason = "Superseded by new invoice bed reservation"
        old_bed = session.get(Bed, existing.bed_id)
        if old_bed is not None and old_bed.status == "RESERVED" and not _has_confirmed_allocation(session, old_bed.id):
            old_bed.status = "AVAILABLE"
            _log_bed_event(
                session,
                bed_id=old_bed.id,
                event_type="BED_RELEASED",
                user_id=user_id,
                invoice_id=invoice_id,
                tenant_id=tenant_id,
                detail={"reservation_id": existing.id, "reason": "invoice_reservation_moved"},
            )

    active_on_bed = session.execute(
        select(BedReservation.id)
        .where(BedReservation.bed_id == bed_id, BedReservation.status == "ACTIVE")
        .limit(1)
    ).scalar_one_or_none()
    if active_on_bed is not None:
        raise ValueError("Bed already has an active reservation.")

    reservation = BedReservation(
        bed_id=bed_id,
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        status="ACTIVE",
        reserved_at=now,
        expires_at=hold_until,
        reserved_by=user_id,
    )
    session.add(reservation)
    session.flush()

    bed.status = "RESERVED"
    _log_bed_event(
        session,
        bed_id=bed.id,
        event_type="RESERVATION_CREATED",
        user_id=user_id,
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        detail={"reservation_id": reservation.id, "expires_at": hold_until.isoformat()},
    )
    return reservation


def release_reservation_on_payment(
    session: Session,
    *,
    invoice_id: int,
    user_id: int | None,
    now: datetime,
    reason: str,
) -> int:
    reservations = (
        session.execute(
            select(BedReservation)
            .where(BedReservation.invoice_id == invoice_id, BedReservation.status == "ACTIVE")
            .with_for_update()
        )
        .scalars()
        .all()
    )
    released = 0
    for reservation in reservations:
        reservation.status = "CANCELLED"
        reservation.cancelled_at = now
        reservation.cancelled_by = user_id
        reservation.cancel_reason = reason
        bed = session.get(Bed, reservation.bed_id)
        if bed is not None and bed.status == "RESERVED" and not _has_confirmed_allocation(session, bed.id):
            bed.status = "AVAILABLE"
            _log_bed_event(
                session,
                bed_id=bed.id,
                event_type="BED_RELEASED",
                user_id=user_id,
                invoice_id=invoice_id,
                tenant_id=reservation.tenant_id,
                detail={"reservation_id": reservation.id, "reason": reason},
            )
        _log_bed_event(
            session,
            bed_id=reservation.bed_id,
            event_type="RESERVATION_CANCELLED",
            user_id=user_id,
            invoice_id=invoice_id,
            tenant_id=reservation.tenant_id,
            detail={"reservation_id": reservation.id, "reason": reason},
        )
        released += 1
    return released


def expire_reservations_batch(session: Session, *, now: datetime, limit: int) -> int:
    reservations = (
        session.execute(
            select(BedReservation)
            .where(
                BedReservation.status == "ACTIVE",
                BedReservation.expires_at.is_not(None),
                BedReservation.expires_at < now,
                sa.or_(
                    BedReservation.invoice_id.is_(None),
                    sa.exists(
                        select(Invoice.id).where(
                            Invoice.id == BedReservation.invoice_id,
                            Invoice.status.in_(tuple(UNPAID_INVOICE_STATUSES)),
                        )
                    ),
                ),
            )
            .order_by(BedReservation.expires_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )

    processed = 0
    for reservation in reservations:
        reservation.status = "EXPIRED"
        if reservation.invoice_id is not None:
            invoice = session.get(Invoice, reservation.invoice_id)
            if (
                invoice is not None
                and invoice.status in UNPAID_INVOICE_STATUSES
                and invoice.reserved_bed_id == reservation.bed_id
            ):
                invoice.reserved_bed_id = None
        bed = session.get(Bed, reservation.bed_id)
        _log_bed_event(
            session,
            bed_id=reservation.bed_id,
            event_type="RESERVATION_EXPIRED",
            user_id=None,
            invoice_id=reservation.invoice_id,
            tenant_id=reservation.tenant_id,
            detail={"reservation_id": reservation.id},
        )
        if reservation.invoice_id is not None:
            _log_bed_event(
                session,
                bed_id=reservation.bed_id,
                event_type="INVOICE_HOLD_EXPIRED",
                user_id=None,
                invoice_id=reservation.invoice_id,
                tenant_id=reservation.tenant_id,
                detail={"reservation_id": reservation.id, "hold_cleared": True},
            )
        if bed is not None and bed.status == "RESERVED" and not _has_confirmed_allocation(session, bed.id):
            bed.status = "AVAILABLE"
            _log_bed_event(
                session,
                bed_id=bed.id,
                event_type="BED_RELEASED",
                user_id=None,
                invoice_id=reservation.invoice_id,
                tenant_id=reservation.tenant_id,
                detail={"reservation_id": reservation.id, "reason": "reservation_expired"},
            )
        processed += 1
    return processed
