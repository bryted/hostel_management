from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Allocation, Bed, BedEvent, BedReservation, Tenant
from app.services.lifecycle import (
    cancel_reservation_hold,
    end_allocation_stay,
    extend_reservation_hold,
    set_bed_maintenance_status,
    transfer_allocation_bed,
)


def test_extend_and_cancel_reservation_hold(factory, db_session):
    block = factory.create_block("Life-Block-A")
    floor = factory.create_floor(block, "F1")
    room = factory.create_room(block, floor, room_code="L-101", room_type="1_IN_ROOM", beds_count=1)
    bed = factory.create_bed(room, 1, status="RESERVED")
    tenant = factory.create_tenant("Lifecycle Tenant A")
    user = factory.create_user("lifecycle-admin-a@example.com")
    invoice = factory.create_invoice(tenant, user=user, reserved_bed=bed, status="approved")
    reservation = factory.create_reservation(bed, tenant=tenant, invoice=invoice, user=user)

    old_expiry = reservation.expires_at
    extend_reservation_hold(
        db_session,
        reservation_id=reservation.id,
        extra_hours=24,
        user_id=user.id,
        reason="Customer requested extra day",
        now=factory.now(),
    )
    assert reservation.expires_at == old_expiry + timedelta(hours=24)
    assert reservation.extension_count == 1

    cancel_reservation_hold(
        db_session,
        reservation_id=reservation.id,
        user_id=user.id,
        reason="Cancelled by staff",
        now=factory.now(),
    )
    assert reservation.status == "CANCELLED"
    bed_db = db_session.get(Bed, bed.id)
    assert bed_db is not None and bed_db.status == "AVAILABLE"


def test_end_allocation_marks_bed_available_and_tenant_inactive(factory, db_session):
    block = factory.create_block("Life-Block-B")
    floor = factory.create_floor(block, "F1")
    room = factory.create_room(block, floor, room_code="L-201", room_type="1_IN_ROOM", beds_count=1)
    bed = factory.create_bed(room, 1, status="OCCUPIED")
    tenant = factory.create_tenant("Lifecycle Tenant B", status="active")
    user = factory.create_user("lifecycle-admin-b@example.com")
    invoice = factory.create_invoice(tenant, user=user, reserved_bed=bed, status="paid", total=Decimal("1500.00"))
    allocation = factory.create_allocation(bed, tenant=tenant, invoice=invoice, user=user)

    end_allocation_stay(
        db_session,
        allocation_id=allocation.id,
        user_id=user.id,
        now=factory.now(),
        reason="Move out completed",
    )

    allocation_db = db_session.get(Allocation, allocation.id)
    bed_db = db_session.get(Bed, bed.id)
    tenant_db = db_session.get(Tenant, tenant.id)
    assert allocation_db is not None and allocation_db.status == "ENDED"
    assert bed_db is not None and bed_db.status == "AVAILABLE"
    assert tenant_db is not None and tenant_db.status == "inactive"


def test_transfer_allocation_moves_resident_and_logs_bed_events(factory, db_session):
    block = factory.create_block("Life-Block-C")
    floor = factory.create_floor(block, "F1")
    room = factory.create_room(block, floor, room_code="L-301", room_type="2_IN_ROOM", beds_count=2)
    old_bed = factory.create_bed(room, 1, status="OCCUPIED")
    new_bed = factory.create_bed(room, 2, status="AVAILABLE")
    tenant = factory.create_tenant("Lifecycle Tenant C", status="active")
    user = factory.create_user("lifecycle-admin-c@example.com")
    invoice = factory.create_invoice(tenant, user=user, reserved_bed=old_bed, status="paid", total=Decimal("1200.00"))
    allocation = factory.create_allocation(old_bed, tenant=tenant, invoice=invoice, user=user)

    new_allocation = transfer_allocation_bed(
        db_session,
        allocation_id=allocation.id,
        new_bed_id=new_bed.id,
        user_id=user.id,
        now=factory.now(),
        reason="Resident requested transfer",
    )

    old_bed_db = db_session.get(Bed, old_bed.id)
    new_bed_db = db_session.get(Bed, new_bed.id)
    assert old_bed_db is not None and old_bed_db.status == "AVAILABLE"
    assert new_bed_db is not None and new_bed_db.status == "OCCUPIED"
    assert new_allocation.status == "CONFIRMED"

    event_types = set(
        db_session.execute(select(BedEvent.event_type).where(BedEvent.tenant_id == tenant.id)).scalars().all()
    )
    assert "BED_TRANSFERRED_OUT" in event_types
    assert "BED_TRANSFERRED_IN" in event_types


def test_bed_maintenance_requires_no_active_stay(factory, db_session):
    block = factory.create_block("Life-Block-D")
    floor = factory.create_floor(block, "F1")
    room = factory.create_room(block, floor, room_code="L-401", room_type="1_IN_ROOM", beds_count=1)
    bed = factory.create_bed(room, 1, status="AVAILABLE")
    user = factory.create_user("lifecycle-admin-d@example.com")

    set_bed_maintenance_status(
        db_session,
        bed_id=bed.id,
        user_id=user.id,
        now=factory.now(),
        out_of_service=True,
        reason="Repair needed",
    )
    assert bed.status == "OUT_OF_SERVICE"

    set_bed_maintenance_status(
        db_session,
        bed_id=bed.id,
        user_id=user.id,
        now=factory.now(),
        out_of_service=False,
        reason="Repair completed",
    )
    assert bed.status == "AVAILABLE"

    tenant = factory.create_tenant("Lifecycle Tenant D", status="active")
    invoice = factory.create_invoice(tenant, user=user, reserved_bed=bed, status="paid")
    factory.create_allocation(bed, tenant=tenant, invoice=invoice, user=user)
    bed.status = "OCCUPIED"
    db_session.flush()

    with pytest.raises(ValueError, match="End or transfer"):
        set_bed_maintenance_status(
            db_session,
            bed_id=bed.id,
            user_id=user.id,
            now=factory.now(),
            out_of_service=True,
            reason="Should fail",
        )
