from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.reservations import expire_reservations_batch, reserve_bed_for_invoice


def test_reservation_rejects_out_of_service_and_occupied_beds(factory, db_session):
    block = factory.create_block("Res-Block-A")
    floor = factory.create_floor(block, "Res-F1")
    room = factory.create_room(block, floor, room_code="RS-101", room_type="2_IN_ROOM", beds_count=2)
    bed_out = factory.create_bed(room, 1, status="OUT_OF_SERVICE")
    bed_occ = factory.create_bed(room, 2, status="OCCUPIED")

    tenant = factory.create_tenant("Res Tenant")
    admin = factory.create_user("res-admin@example.com")
    invoice = factory.create_invoice(tenant, user=admin, status="approved", total=Decimal("1000.00"))
    now = factory.now()

    with pytest.raises(ValueError, match="out of service"):
        reserve_bed_for_invoice(
            db_session,
            invoice_id=invoice.id,
            tenant_id=tenant.id,
            bed_id=bed_out.id,
            hold_until=factory.now(hours=6),
            user_id=admin.id,
            now=now,
        )

    with pytest.raises(ValueError, match="already occupied"):
        reserve_bed_for_invoice(
            db_session,
            invoice_id=invoice.id,
            tenant_id=tenant.id,
            bed_id=bed_occ.id,
            hold_until=factory.now(hours=6),
            user_id=admin.id,
            now=now,
        )


def test_reservation_rejects_second_live_room_for_same_tenant(factory, db_session):
    block = factory.create_block("Res-Block-B")
    floor = factory.create_floor(block, "Res-F2")
    room = factory.create_room(block, floor, room_code="RS-201", room_type="2_IN_ROOM", beds_count=2)
    bed1 = factory.create_bed(room, 1, status="RESERVED")
    bed2 = factory.create_bed(room, 2, status="AVAILABLE")

    tenant = factory.create_tenant("Reserved Tenant")
    admin = factory.create_user("res-admin-2@example.com")
    invoice_a = factory.create_invoice(tenant, user=admin, status="approved", total=Decimal("1000.00"))
    invoice_b = factory.create_invoice(tenant, user=admin, status="approved", total=Decimal("1200.00"))
    factory.create_reservation(bed1, tenant=tenant, invoice=invoice_a, user=admin)

    with pytest.raises(ValueError, match="already has an active reservation"):
        reserve_bed_for_invoice(
            db_session,
            invoice_id=invoice_b.id,
            tenant_id=tenant.id,
            bed_id=bed2.id,
            hold_until=factory.now(hours=6),
            user_id=admin.id,
            now=factory.now(),
        )


def test_expired_reservation_clears_invoice_reserved_bed(factory, db_session):
    block = factory.create_block("Res-Block-C")
    floor = factory.create_floor(block, "Res-F3")
    room = factory.create_room(block, floor, room_code="RS-301", room_type="1_IN_ROOM", beds_count=1)
    bed = factory.create_bed(room, 1, status="RESERVED")

    tenant = factory.create_tenant("Expired Hold Tenant")
    admin = factory.create_user("res-admin-3@example.com")
    invoice = factory.create_invoice(tenant, user=admin, reserved_bed=bed, status="approved", total=Decimal("1000.00"))
    factory.create_reservation(
        bed,
        tenant=tenant,
        invoice=invoice,
        user=admin,
        expires_at=factory.now(hours=-2),
    )

    processed = expire_reservations_batch(db_session, now=factory.now(), limit=10)

    assert processed == 1
    assert invoice.reserved_bed_id is None
    assert bed.status == "AVAILABLE"
