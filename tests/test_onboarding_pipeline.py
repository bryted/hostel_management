from __future__ import annotations

from decimal import Decimal

from app.services.onboarding import get_onboarding_pipeline, get_onboarding_queue


def test_partially_paid_invoice_only_appears_in_paid_unallocated(factory, db_session):
    tenant = factory.create_tenant("Onboard Tenant 1", status="prospect")
    user = factory.create_user("onboard-admin-1@example.com")

    partially_paid_invoice = factory.create_invoice(tenant, user=user, status="partially_paid", total=Decimal("1000.00"))
    factory.create_payment(tenant, partially_paid_invoice, amount=Decimal("200.00"), user=user)

    approved_unpaid_invoice = factory.create_invoice(tenant, user=user, status="approved", total=Decimal("800.00"))

    queue = get_onboarding_queue(db_session, limit=200)

    partial_rows = [row for row in queue if int(row["Invoice ID"]) == partially_paid_invoice.id]
    assert len(partial_rows) == 1
    assert partial_rows[0]["Stage"] == "Paid unallocated"

    approved_rows = [row for row in queue if int(row["Invoice ID"]) == approved_unpaid_invoice.id]
    assert len(approved_rows) == 1
    assert approved_rows[0]["Stage"] == "Approved unpaid"


def test_onboarding_queue_has_no_duplicate_invoice_rows_and_excludes_rejected(factory, db_session):
    tenant = factory.create_tenant("Onboard Tenant 2", status="prospect")
    user = factory.create_user("onboard-admin-2@example.com")

    approved_invoice = factory.create_invoice(tenant, user=user, status="approved", total=Decimal("500.00"))
    paid_unallocated_invoice = factory.create_invoice(tenant, user=user, status="approved", total=Decimal("900.00"))
    factory.create_payment(tenant, paid_unallocated_invoice, amount=Decimal("100.00"), user=user)

    rejected_invoice = factory.create_invoice(tenant, user=user, status="rejected", total=Decimal("700.00"))
    factory.create_payment(tenant, rejected_invoice, amount=Decimal("50.00"), user=user)

    queue = get_onboarding_queue(db_session, limit=200)
    invoice_ids = [int(row["Invoice ID"]) for row in queue]

    assert len(invoice_ids) == len(set(invoice_ids))
    assert approved_invoice.id in invoice_ids
    assert paid_unallocated_invoice.id in invoice_ids
    assert rejected_invoice.id not in invoice_ids


def test_onboarding_queue_respects_block_floor_filters(factory, db_session):
    admin = factory.create_user("onboard-admin-3@example.com")

    block_a = factory.create_block("Queue-Block-A")
    floor_a = factory.create_floor(block_a, "F1")
    room_a = factory.create_room(block_a, floor_a, room_code="QA-101", room_type="1_IN_ROOM", beds_count=1)
    bed_a = factory.create_bed(room_a, 1, status="AVAILABLE")

    block_b = factory.create_block("Queue-Block-B")
    floor_b = factory.create_floor(block_b, "F1")
    room_b = factory.create_room(block_b, floor_b, room_code="QB-101", room_type="1_IN_ROOM", beds_count=1)
    bed_b = factory.create_bed(room_b, 1, status="AVAILABLE")

    tenant_a = factory.create_tenant("Queue Tenant A", status="prospect")
    tenant_b = factory.create_tenant("Queue Tenant B", status="prospect")

    invoice_a = factory.create_invoice(tenant_a, user=admin, reserved_bed=bed_a, status="approved", total=Decimal("500.00"))
    invoice_b = factory.create_invoice(tenant_b, user=admin, reserved_bed=bed_b, status="approved", total=Decimal("500.00"))
    factory.create_payment(tenant_b, invoice_b, amount=Decimal("50.00"), user=admin)

    queue_a = get_onboarding_queue(db_session, limit=200, block_id=block_a.id, floor_id=floor_a.id)
    queue_b = get_onboarding_queue(db_session, limit=200, block_id=block_b.id, floor_id=floor_b.id)

    assert [int(row["Invoice ID"]) for row in queue_a] == [invoice_a.id]
    assert [int(row["Invoice ID"]) for row in queue_b] == [invoice_b.id]


def test_onboarding_queue_uses_active_reservation_location_when_invoice_reserved_bed_is_null(factory, db_session):
    admin = factory.create_user("onboard-admin-4@example.com")
    block = factory.create_block("Queue-Block-NullBed")
    floor = factory.create_floor(block, "F1")
    room = factory.create_room(block, floor, room_code="QN-101", room_type="1_IN_ROOM", beds_count=1)
    bed = factory.create_bed(room, 1, status="AVAILABLE")

    tenant = factory.create_tenant("Queue Tenant NullBed", status="prospect")
    invoice = factory.create_invoice(
        tenant,
        user=admin,
        reserved_bed=None,
        status="approved",
        total=Decimal("650.00"),
    )
    factory.create_reservation(bed, tenant=tenant, invoice=invoice, user=admin)

    rows = get_onboarding_queue(db_session, limit=200, block_id=block.id, floor_id=floor.id)
    ids = [int(row["Invoice ID"]) for row in rows]

    assert invoice.id in ids


def test_onboarding_pipeline_counts_match_queue_stage_counts(factory, db_session):
    admin = factory.create_user("onboard-admin-5@example.com")
    tenant = factory.create_tenant("Queue Tenant Metrics", status="prospect")

    invoice_approved = factory.create_invoice(tenant, user=admin, status="approved", total=Decimal("500.00"))
    invoice_paid = factory.create_invoice(tenant, user=admin, status="approved", total=Decimal("700.00"))
    factory.create_payment(tenant, invoice_paid, amount=Decimal("100.00"), user=admin)

    queue = get_onboarding_queue(db_session, limit=200)
    pipeline = get_onboarding_pipeline(db_session, as_of=factory.now())

    approved_count = sum(1 for row in queue if row.get("Stage") == "Approved unpaid")
    paid_count = sum(1 for row in queue if row.get("Stage") == "Paid unallocated")

    assert invoice_approved.id in [int(row["Invoice ID"]) for row in queue]
    assert invoice_paid.id in [int(row["Invoice ID"]) for row in queue]
    assert pipeline.prospects_with_approved_unpaid == approved_count
    assert pipeline.paid_unallocated_tenants == paid_count
