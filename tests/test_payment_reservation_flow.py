from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

import pytest

from app.models import Allocation, Bed, BedEvent, BedReservation
from app.services.invoicing import record_payment


def test_payment_releases_active_reservation_and_logs_events(factory, db_session):
    block = factory.create_block("Pay-Block")
    floor = factory.create_floor(block, "Pay-F1")
    room = factory.create_room(
        block,
        floor,
        room_code="PAY-101",
        room_type="1_IN_ROOM",
        beds_count=1,
        unit_price_per_bed=Decimal("1500.00"),
    )
    bed = factory.create_bed(room, 1, status="AVAILABLE")
    tenant = factory.create_tenant("Pay Tenant")
    user = factory.create_user("pay-admin@example.com")
    now = factory.now()

    invoice = create_invoice(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        reserved_bed_id=bed.id,
        currency="GHS",
        tax=Decimal("0"),
        discount=Decimal("0"),
        notes=None,
        status="approved",
        due_at=now,
        hold_until=now,
        now=now,
    )

    reservation = db_session.execute(
        select(BedReservation).where(BedReservation.invoice_id == invoice.id, BedReservation.status == "ACTIVE")
    ).scalar_one()
    bed_db = db_session.get(Bed, bed.id)
    assert bed_db is not None and bed_db.status == "RESERVED"
    assert reservation.invoice_id == invoice.id

    payment, _receipt, paid_total = record_payment(
        db_session,
        invoice=invoice,
        user_id=user.id,
        amount=Decimal("1500.00"),
        method="cash",
        reference="PAY-REF-1",
        now=factory.now(),
    )

    assert payment.id is not None
    assert paid_total == Decimal("1500.00")

    reservation_after = db_session.get(BedReservation, reservation.id)
    bed_after = db_session.get(Bed, bed.id)
    assert reservation_after is not None and reservation_after.status == "CANCELLED"
    assert bed_after is not None and bed_after.status == "AVAILABLE"

    event_types = set(
        db_session.execute(
            select(BedEvent.event_type).where(BedEvent.bed_id == bed.id)
        )
        .scalars()
        .all()
    )
    assert "RESERVATION_CANCELLED" in event_types
    assert "BED_RELEASED" in event_types


def test_payment_rejected_when_tenant_already_has_active_allocation(factory, db_session):
    block = factory.create_block("Pay-Block-B")
    floor = factory.create_floor(block, "Pay-F2")
    room = factory.create_room(
        block,
        floor,
        room_code="PAY-201",
        room_type="2_IN_ROOM",
        beds_count=2,
        unit_price_per_bed=Decimal("1200.00"),
    )
    occupied_bed = factory.create_bed(room, 1, status="OCCUPIED")
    reserved_bed = factory.create_bed(room, 2, status="AVAILABLE")
    tenant = factory.create_tenant("Double Pay Tenant")
    user = factory.create_user("pay-admin-2@example.com")
    active_invoice = factory.create_invoice(tenant, user=user, status="paid", total=Decimal("1200.00"))
    factory.create_allocation(occupied_bed, tenant=tenant, invoice=active_invoice, user=user)
    invoice = factory.create_invoice(
        tenant,
        user=user,
        reserved_bed=reserved_bed,
        status="approved",
        total=Decimal("1200.00"),
    )

    with pytest.raises(ValueError, match="active bed allocation"):
        record_payment(
            db_session,
            invoice=invoice,
            user_id=user.id,
            amount=Decimal("100.00"),
            method="cash",
            reference="PAY-REF-2",
            now=factory.now(),
        )

    allocations = db_session.execute(
        select(Allocation).where(Allocation.tenant_id == tenant.id, Allocation.status == "CONFIRMED")
    ).scalars().all()
    assert len(allocations) == 1
