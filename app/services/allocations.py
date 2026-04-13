from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Allocation,
    AllocationEvent,
    Bed,
    BedEvent,
    BedReservation,
    Invoice,
    InvoiceEvent,
    Tenant,
    TenantEvent,
    User,
)
from app.services.academic_years import resolve_academic_year
from app.services.common import bed_is_in_operational_inventory
from app.services.invoicing import get_paid_total
from app.services.types import AllocationResult


def _paid_total_for_invoice(session: Session, invoice_id: int) -> Decimal:
    return get_paid_total(session, invoice_id)


def assign_bed_for_paid_invoice(
    session: Session,
    invoice_id: int,
    bed_id: int,
    user_id: int,
    now: datetime,
) -> AllocationResult:
    actor = session.get(User, user_id)
    if actor is None or not bool(actor.is_active):
        raise PermissionError("Active user required to confirm allocation.")
    if not bool(actor.is_admin):
        raise PermissionError("Only admin users can confirm allocations.")

    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise ValueError("Invoice not found.")

    paid_total = _paid_total_for_invoice(session, invoice.id)
    if paid_total <= Decimal("0"):
        raise ValueError("Invoice must have at least one successful payment before allocation.")

    existing_invoice_allocation = session.execute(
        select(Allocation.id).where(
            Allocation.invoice_id == invoice.id,
            Allocation.status == "CONFIRMED",
        )
    ).scalar_one_or_none()
    if existing_invoice_allocation is not None:
        raise ValueError("Invoice already has a confirmed allocation.")

    existing_tenant_allocation = session.execute(
        select(Allocation.id).where(
            Allocation.tenant_id == invoice.tenant_id,
            Allocation.status == "CONFIRMED",
            Allocation.invoice_id != invoice.id,
        )
    ).scalar_one_or_none()
    if existing_tenant_allocation is not None:
        raise ValueError(
            "Tenant already has a confirmed allocation. End or transfer the current stay before assigning another bed."
        )

    bed = session.get(Bed, bed_id)
    if bed is None:
        raise ValueError("Bed not found.")
    if not bed_is_in_operational_inventory(session, int(bed.id)):
        raise ValueError("Bed is in inactive inventory.")
    if bed.status == "OUT_OF_SERVICE":
        raise ValueError("Bed is out of service.")
    if bed.status == "OCCUPIED":
        raise ValueError("Bed is already occupied.")

    existing_bed_allocation = session.execute(
        select(Allocation.id).where(
            Allocation.bed_id == bed.id,
            Allocation.status == "CONFIRMED",
        )
    ).scalar_one_or_none()
    if existing_bed_allocation is not None:
        raise ValueError("Bed already has a confirmed allocation.")

    active_bed_reservation_row = session.execute(
        select(BedReservation.id, BedReservation.invoice_id)
        .where(BedReservation.bed_id == bed.id, BedReservation.status == "ACTIVE")
        .limit(1)
    ).first()
    if active_bed_reservation_row is not None:
        _reservation_id, reservation_invoice_id = active_bed_reservation_row
        if reservation_invoice_id is None or int(reservation_invoice_id) != int(invoice.id):
            raise ValueError("Bed has an active reservation for another invoice.")

    if bed.status not in {"AVAILABLE", "RESERVED"}:
        raise ValueError("Bed is not assignable.")

    # Cancel stale reservation rows tied to this invoice to prevent ghost reserved signals.
    active_reservations = (
        session.execute(
            select(BedReservation)
            .where(BedReservation.invoice_id == invoice.id, BedReservation.status == "ACTIVE")
            .with_for_update()
        )
        .scalars()
        .all()
    )
    for reservation in active_reservations:
        reservation.status = "CANCELLED"
        reservation.cancelled_at = now
        reservation.cancelled_by = user_id
        reservation.cancel_reason = "Allocation confirmed"

    allocation = Allocation(
        bed_id=bed.id,
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        academic_year_id=invoice.academic_year_id or resolve_academic_year(session, as_of=now).id,
        status="CONFIRMED",
        start_date=now,
    )
    session.add(allocation)
    try:
        session.flush()
    except IntegrityError as exc:
        raise ValueError(
            "Allocation could not be confirmed because data changed concurrently. Refresh and retry."
        ) from exc

    invoice.reserved_bed_id = bed.id
    bed.status = "OCCUPIED"

    session.add(
        AllocationEvent(
            allocation_id=allocation.id,
            event_type="ALLOCATION_CONFIRMED",
            user_id=user_id,
            detail_json={
                "invoice_id": invoice.id,
                "tenant_id": invoice.tenant_id,
                "bed_id": bed.id,
                "user_id": user_id,
                "at": now.isoformat(),
            },
        )
    )
    session.add(
        BedEvent(
            bed_id=bed.id,
            event_type="ALLOCATION_CONFIRMED",
            user_id=user_id,
            invoice_id=invoice.id,
            tenant_id=invoice.tenant_id,
            detail_json={
                "allocation_id": allocation.id,
                "invoice_id": invoice.id,
                "tenant_id": invoice.tenant_id,
                "bed_id": bed.id,
                "user_id": user_id,
                "at": now.isoformat(),
            },
        )
    )
    session.add(
        InvoiceEvent(
            invoice_id=invoice.id,
            event_type="allocation_confirmed",
            payload={
                "allocation_id": allocation.id,
                "tenant_id": invoice.tenant_id,
                "bed_id": bed.id,
                "user_id": user_id,
                "at": now.isoformat(),
            },
        )
    )

    tenant = session.get(Tenant, invoice.tenant_id)
    if tenant is not None:
        if tenant.status != "active":
            tenant.status = "active"
        session.add(
            TenantEvent(
                tenant_id=tenant.id,
                event_type="TENANT_CONFIRMED",
                event_at=now,
                user_id=user_id,
                detail_json={
                    "invoice_id": invoice.id,
                    "allocation_id": allocation.id,
                    "bed_id": bed.id,
                    "tenant_id": tenant.id,
                    "user_id": user_id,
                    "at": now.isoformat(),
                },
            )
        )

    return AllocationResult(
        allocation_id=allocation.id,
        invoice_id=invoice.id,
        bed_id=bed.id,
        tenant_id=invoice.tenant_id,
        bed_status=bed.status,
        created=True,
    )
