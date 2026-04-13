from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

import pytest

from app.models import Allocation, Bed, BedEvent, BedReservation, PaymentAllocation
from app.services.invoicing import create_invoice, get_paid_total, record_payment, record_tenant_payment


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
        hold_until=factory.now(hours=24),
        now=now,
    )

    reservation = db_session.execute(
        select(BedReservation).where(BedReservation.invoice_id == invoice.id, BedReservation.status == "ACTIVE")
    ).scalar_one()
    bed_db = db_session.get(Bed, bed.id)
    assert bed_db is not None and bed_db.status == "RESERVED"
    assert reservation.invoice_id == invoice.id

    payment, receipt, paid_total = record_payment(
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
    assert invoice.academic_year_id is not None
    assert reservation.academic_year_id == invoice.academic_year_id
    assert payment.academic_year_id == invoice.academic_year_id
    assert receipt.academic_year_id == invoice.academic_year_id

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


def test_tenant_payment_can_split_across_multiple_invoices(factory, db_session):
    block = factory.create_block("Split-Pay-Block")
    floor = factory.create_floor(block, "Split-F1")
    room = factory.create_room(
        block,
        floor,
        room_code="SPL-101",
        room_type="2_IN_ROOM",
        beds_count=2,
        unit_price_per_bed=Decimal("1000.00"),
    )
    bed_a = factory.create_bed(room, 1, status="AVAILABLE")
    bed_b = factory.create_bed(room, 2, status="AVAILABLE")
    tenant = factory.create_tenant("Split Pay Tenant")
    user = factory.create_user("split-pay-admin@example.com")
    now = factory.now()

    invoice_a = factory.create_invoice(
        tenant,
        user=user,
        reserved_bed=bed_a,
        status="approved",
        total=Decimal("1000.00"),
    )
    invoice_b = create_invoice(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        reserved_bed_id=bed_b.id,
        currency="GHS",
        tax=Decimal("0"),
        discount=Decimal("0"),
        notes=None,
        status="approved",
        due_at=now,
        hold_until=factory.now(hours=24),
        now=now,
    )

    payment, receipt, invoice_totals = record_tenant_payment(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        amount=Decimal("1500.00"),
        method="bank_transfer",
        reference="SPLIT-REF-1",
        allocations=[
            {"invoice_id": invoice_a.id, "amount": Decimal("1000.00")},
            {"invoice_id": invoice_b.id, "amount": Decimal("200.00")},
        ],
        now=factory.now(),
    )

    allocation_rows = db_session.execute(
        select(PaymentAllocation).where(PaymentAllocation.payment_id == payment.id).order_by(PaymentAllocation.id.asc())
    ).scalars().all()
    reservation_rows = db_session.execute(
        select(BedReservation).where(BedReservation.invoice_id.in_([invoice_a.id, invoice_b.id])).order_by(BedReservation.id.asc())
    ).scalars().all()

    assert receipt.payment_id == payment.id
    assert len(allocation_rows) == 2
    assert {int(row.invoice_id) for row in allocation_rows} == {int(invoice_a.id), int(invoice_b.id)}
    assert invoice_totals[int(invoice_a.id)] == Decimal("1000.00")
    assert invoice_totals[int(invoice_b.id)] == Decimal("200.00")
    assert get_paid_total(db_session, int(invoice_a.id)) == Decimal("1000.00")
    assert get_paid_total(db_session, int(invoice_b.id)) == Decimal("200.00")
    assert invoice_a.status == "paid"
    assert invoice_b.status == "partially_paid"
    assert all(reservation.status == "CANCELLED" for reservation in reservation_rows)
