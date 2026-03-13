from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Allocation, Bed
from app.services.allocations import assign_bed_for_paid_invoice


def test_paid_invoice_assignment_confirms_allocation_and_marks_bed_occupied(factory, db_session):
    block = factory.create_block("Alloc-Block-A")
    floor = factory.create_floor(block, "Alloc-F1")
    room = factory.create_room(block, floor, room_code="AL-101", room_type="1_IN_ROOM", beds_count=1)
    bed = factory.create_bed(room, 1, status="AVAILABLE")

    tenant = factory.create_tenant("Alloc Tenant")
    user = factory.create_user("alloc-admin@example.com")
    invoice = factory.create_invoice(tenant, user=user, status="approved", total=Decimal("1200.00"))
    factory.create_payment(tenant, invoice, amount=Decimal("300.00"), user=user)

    result = assign_bed_for_paid_invoice(
        db_session,
        invoice_id=invoice.id,
        bed_id=bed.id,
        user_id=user.id,
        now=factory.now(),
    )

    confirmed = db_session.execute(
        select(Allocation).where(Allocation.invoice_id == invoice.id, Allocation.status == "CONFIRMED")
    ).scalar_one()
    bed_db = db_session.get(Bed, bed.id)

    assert result.created is True
    assert result.allocation_id == confirmed.id
    assert bed_db is not None and bed_db.status == "OCCUPIED"


def test_assignment_rejected_when_invoice_has_no_successful_payment(factory, db_session):
    block = factory.create_block("Alloc-Block-B")
    floor = factory.create_floor(block, "Alloc-F2")
    room = factory.create_room(block, floor, room_code="AL-201", room_type="1_IN_ROOM", beds_count=1)
    bed = factory.create_bed(room, 1, status="AVAILABLE")

    tenant = factory.create_tenant("NoPay Tenant")
    user = factory.create_user("alloc-admin-2@example.com")
    invoice = factory.create_invoice(tenant, user=user, status="approved", total=Decimal("1000.00"))

    with pytest.raises(ValueError, match="at least one successful payment"):
        assign_bed_for_paid_invoice(
            db_session,
            invoice_id=invoice.id,
            bed_id=bed.id,
            user_id=user.id,
            now=factory.now(),
        )


def test_assignment_rejected_for_conflicting_reservation_or_allocation(factory, db_session):
    block = factory.create_block("Alloc-Block-C")
    floor = factory.create_floor(block, "Alloc-F3")
    room = factory.create_room(block, floor, room_code="AL-301", room_type="2_IN_ROOM", beds_count=2)
    bed1 = factory.create_bed(room, 1, status="RESERVED")
    bed2 = factory.create_bed(room, 2, status="AVAILABLE")

    user = factory.create_user("alloc-admin-3@example.com")
    tenant_a = factory.create_tenant("Alloc Tenant A")
    tenant_b = factory.create_tenant("Alloc Tenant B")

    invoice_target = factory.create_invoice(tenant_a, user=user, status="approved", total=Decimal("1000.00"))
    factory.create_payment(tenant_a, invoice_target, amount=Decimal("100.00"), user=user)

    invoice_other = factory.create_invoice(tenant_b, user=user, status="approved", total=Decimal("900.00"))
    factory.create_reservation(bed1, tenant=tenant_b, invoice=invoice_other, user=user)

    with pytest.raises(ValueError, match="active reservation for another invoice"):
        assign_bed_for_paid_invoice(
            db_session,
            invoice_id=invoice_target.id,
            bed_id=bed1.id,
            user_id=user.id,
            now=factory.now(),
        )

    existing = factory.create_invoice(tenant_b, user=user, status="approved", total=Decimal("750.00"))
    factory.create_payment(tenant_b, existing, amount=Decimal("200.00"), user=user)
    factory.create_allocation(bed2, tenant=tenant_b, invoice=existing, user=user)
    bed2.status = "OCCUPIED"
    db_session.flush()

    with pytest.raises(ValueError, match="already occupied|confirmed allocation"):
        assign_bed_for_paid_invoice(
            db_session,
            invoice_id=invoice_target.id,
            bed_id=bed2.id,
            user_id=user.id,
            now=factory.now(),
        )


def test_assignment_rejected_for_non_admin_user(factory, db_session):
    block = factory.create_block("Alloc-Block-D")
    floor = factory.create_floor(block, "Alloc-F4")
    room = factory.create_room(block, floor, room_code="AL-401", room_type="1_IN_ROOM", beds_count=1)
    bed = factory.create_bed(room, 1, status="AVAILABLE")

    tenant = factory.create_tenant("Alloc Tenant C")
    admin = factory.create_user("alloc-admin-4@example.com", is_admin=True)
    cashier = factory.create_user("alloc-cashier@example.com", is_admin=False)
    invoice = factory.create_invoice(tenant, user=admin, status="approved", total=Decimal("1000.00"))
    factory.create_payment(tenant, invoice, amount=Decimal("400.00"), user=admin)

    with pytest.raises(PermissionError, match="Only admin users"):
        assign_bed_for_paid_invoice(
            db_session,
            invoice_id=invoice.id,
            bed_id=bed.id,
            user_id=cashier.id,
            now=factory.now(),
        )


def test_assignment_rejected_when_tenant_already_has_confirmed_allocation(factory, db_session):
    block = factory.create_block("Alloc-Block-E")
    floor = factory.create_floor(block, "Alloc-F5")
    room = factory.create_room(block, floor, room_code="AL-501", room_type="2_IN_ROOM", beds_count=2)
    bed1 = factory.create_bed(room, 1, status="OCCUPIED")
    bed2 = factory.create_bed(room, 2, status="AVAILABLE")

    tenant = factory.create_tenant("Alloc Tenant D")
    user = factory.create_user("alloc-admin-5@example.com")

    current_invoice = factory.create_invoice(tenant, user=user, status="paid", total=Decimal("1000.00"))
    factory.create_allocation(bed1, tenant=tenant, invoice=current_invoice, user=user)

    new_invoice = factory.create_invoice(tenant, user=user, status="approved", total=Decimal("1200.00"))
    factory.create_payment(tenant, new_invoice, amount=Decimal("300.00"), user=user)

    with pytest.raises(ValueError, match="already has a confirmed allocation"):
        assign_bed_for_paid_invoice(
            db_session,
            invoice_id=new_invoice.id,
            bed_id=bed2.id,
            user_id=user.id,
            now=factory.now(),
        )
