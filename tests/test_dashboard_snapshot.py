from __future__ import annotations

from decimal import Decimal
from datetime import timezone

from app.services.dashboard_metrics import get_dashboard_snapshot
from app.services.reservations import expire_reservations_batch


def test_dashboard_snapshot_bed_rows_include_location_columns(factory, db_session):
    block = factory.create_block("Dash-Block-A")
    floor = factory.create_floor(block, "Dash-Floor-1")
    room = factory.create_room(block, floor, room_code="D-A-101", room_type="2_IN_ROOM", beds_count=2)
    bed1 = factory.create_bed(room, 1, status="AVAILABLE")
    bed2 = factory.create_bed(room, 2, status="RESERVED")

    tenant = factory.create_tenant("Dash Tenant")
    user = factory.create_user("dash-admin@example.com")
    invoice = factory.create_invoice(tenant, user=user, reserved_bed=bed2, status="approved")
    factory.create_reservation(bed2, tenant=tenant, invoice=invoice, user=user)

    snapshot = get_dashboard_snapshot(
        db_session,
        as_of=factory.now().astimezone(timezone.utc),
        currency="GHS",
        block_id=block.id,
        floor_id=floor.id,
        include_occupancy_tables=False,
    )

    assert snapshot.block_occupancy_rows == []
    assert snapshot.floor_occupancy_rows == []
    assert len(snapshot.bed_availability_rows) == 2

    expected_columns = {
        "Block",
        "Floor",
        "Room",
        "Bed",
        "Status",
        "Price/bed",
        "Reservation Expires",
        "Invoice",
        "Tenant",
    }
    assert expected_columns.issubset(snapshot.bed_availability_rows[0].keys())
    assert all(row["Block"] == block.name for row in snapshot.bed_availability_rows)
    assert all(row["Floor"] == floor.floor_label for row in snapshot.bed_availability_rows)
    assert {row["Bed"] for row in snapshot.bed_availability_rows} == {bed1.bed_label, bed2.bed_label}


def test_dashboard_snapshot_bed_rows_respect_block_floor_filters(factory, db_session):
    block_a = factory.create_block("Dash-Block-Filt-A")
    block_b = factory.create_block("Dash-Block-Filt-B")
    floor_a1 = factory.create_floor(block_a, "F1")
    floor_a2 = factory.create_floor(block_a, "F2")
    floor_b1 = factory.create_floor(block_b, "F1")

    room_a1 = factory.create_room(block_a, floor_a1, room_code="A101", room_type="1_IN_ROOM", beds_count=1)
    room_a2 = factory.create_room(block_a, floor_a2, room_code="A201", room_type="1_IN_ROOM", beds_count=1)
    room_b1 = factory.create_room(block_b, floor_b1, room_code="B101", room_type="1_IN_ROOM", beds_count=1)

    factory.create_bed(room_a1, 1, status="AVAILABLE")
    factory.create_bed(room_a2, 1, status="AVAILABLE")
    factory.create_bed(room_b1, 1, status="AVAILABLE")

    snapshot_a1 = get_dashboard_snapshot(
        db_session,
        as_of=factory.now(),
        currency="GHS",
        block_id=block_a.id,
        floor_id=floor_a1.id,
        include_occupancy_tables=False,
    )
    snapshot_b1 = get_dashboard_snapshot(
        db_session,
        as_of=factory.now(),
        currency="GHS",
        block_id=block_b.id,
        floor_id=floor_b1.id,
        include_occupancy_tables=False,
    )

    assert len(snapshot_a1.bed_availability_rows) == 1
    assert snapshot_a1.bed_availability_rows[0]["Block"] == block_a.name
    assert snapshot_a1.bed_availability_rows[0]["Floor"] == floor_a1.floor_label

    assert len(snapshot_b1.bed_availability_rows) == 1
    assert snapshot_b1.bed_availability_rows[0]["Block"] == block_b.name
    assert snapshot_b1.bed_availability_rows[0]["Floor"] == floor_b1.floor_label


def test_dashboard_alert_counts_follow_block_floor_filters(factory, db_session):
    block_a = factory.create_block("Dash-Alert-A")
    block_b = factory.create_block("Dash-Alert-B")
    floor_a = factory.create_floor(block_a, "F1")
    floor_b = factory.create_floor(block_b, "F1")
    room_a = factory.create_room(block_a, floor_a, room_code="A-101", room_type="1_IN_ROOM", beds_count=1)
    room_b = factory.create_room(block_b, floor_b, room_code="B-101", room_type="1_IN_ROOM", beds_count=1)
    bed_a = factory.create_bed(room_a, 1, status="AVAILABLE")
    bed_b = factory.create_bed(room_b, 1, status="AVAILABLE")

    user = factory.create_user("dash-alert-admin@example.com")
    tenant_a = factory.create_tenant("Dash Alert Tenant A")
    tenant_b = factory.create_tenant("Dash Alert Tenant B")

    invoice_a = factory.create_invoice(
        tenant_a,
        user=user,
        reserved_bed=bed_a,
        status="approved",
        total=Decimal("1000.00"),
    )
    invoice_b = factory.create_invoice(
        tenant_b,
        user=user,
        reserved_bed=bed_b,
        status="approved",
        total=Decimal("900.00"),
    )
    factory.create_payment(tenant_b, invoice_b, amount=Decimal("100.00"), user=user)

    snapshot_a = get_dashboard_snapshot(
        db_session,
        as_of=factory.now().astimezone(timezone.utc),
        currency="GHS",
        block_id=block_a.id,
        floor_id=floor_a.id,
        include_occupancy_tables=False,
    )
    snapshot_b = get_dashboard_snapshot(
        db_session,
        as_of=factory.now().astimezone(timezone.utc),
        currency="GHS",
        block_id=block_b.id,
        floor_id=floor_b.id,
        include_occupancy_tables=False,
    )

    assert snapshot_a.alerts.approved_unpaid_count == 1
    assert snapshot_a.alerts.paid_unallocated_count == 0
    assert snapshot_a.onboarding.prospects_with_approved_unpaid == 1
    assert snapshot_a.onboarding.paid_unallocated_tenants == 0
    assert invoice_a.id != invoice_b.id

    assert snapshot_b.alerts.approved_unpaid_count == 0
    assert snapshot_b.alerts.paid_unallocated_count == 1
    assert snapshot_b.onboarding.prospects_with_approved_unpaid == 0
    assert snapshot_b.onboarding.paid_unallocated_tenants == 1


def test_dashboard_outstanding_excludes_expired_hold_invoices(factory, db_session):
    block = factory.create_block("Dash-Outstanding-A")
    floor = factory.create_floor(block, "F1")
    room = factory.create_room(block, floor, room_code="DO-101", room_type="1_IN_ROOM", beds_count=1)
    bed = factory.create_bed(room, 1, status="RESERVED")

    user = factory.create_user("dash-outstanding-admin@example.com")
    tenant = factory.create_tenant("Dash Outstanding Tenant")
    invoice = factory.create_invoice(
        tenant,
        user=user,
        reserved_bed=bed,
        status="approved",
        total=Decimal("1600.00"),
    )
    factory.create_reservation(
        bed,
        tenant=tenant,
        invoice=invoice,
        user=user,
        expires_at=factory.now(hours=-3),
    )
    expire_reservations_batch(db_session, now=factory.now(), limit=10)

    snapshot = get_dashboard_snapshot(
        db_session,
        as_of=factory.now().astimezone(timezone.utc),
        currency="GHS",
        include_occupancy_tables=False,
    )

    assert snapshot.finance.outstanding == Decimal("0")
