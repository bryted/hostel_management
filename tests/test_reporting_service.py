from __future__ import annotations

from decimal import Decimal

from app.services.reporting import get_reporting_tables
from app.services.reservations import expire_reservations_batch


def test_reporting_tables_include_collections_aging_and_utilization(factory, db_session):
    block = factory.create_block("Report-Block-A")
    floor = factory.create_floor(block, "F1")
    room = factory.create_room(block, floor, room_code="RPT-101", room_type="2_IN_ROOM", beds_count=2)
    bed1 = factory.create_bed(room, 1, status="AVAILABLE")
    bed2 = factory.create_bed(room, 2, status="OUT_OF_SERVICE")

    user = factory.create_user("report-admin@example.com")
    tenant_a = factory.create_tenant("Report Tenant A", status="prospect")
    tenant_b = factory.create_tenant("Report Tenant B", status="active")

    invoice_paid = factory.create_invoice(tenant_a, user=user, reserved_bed=bed1, status="paid", total=Decimal("1000.00"))
    invoice_outstanding = factory.create_invoice(tenant_b, user=user, reserved_bed=bed1, status="approved", total=Decimal("1500.00"))
    factory.create_payment(tenant_a, invoice_paid, amount=Decimal("1000.00"), user=user)

    tables = get_reporting_tables(
        db_session,
        start_date=factory.now().date(),
        end_date=factory.now().date(),
        currency="GHS",
    )

    assert tables["collections_by_method"]
    assert any(row["Method"] == "cash" for row in tables["collections_by_method"])
    assert tables["aging_rows"]
    assert any(row["Invoice"] == invoice_outstanding.invoice_no for row in tables["aging_rows"])
    assert tables["room_utilization"]
    assert any(row["Room"] == room.room_code for row in tables["room_utilization"])
    assert tables["conversion_rows"]


def test_reporting_aging_excludes_expired_hold_invoices(factory, db_session):
    block = factory.create_block("Report-Block-B")
    floor = factory.create_floor(block, "F2")
    room = factory.create_room(block, floor, room_code="RPT-201", room_type="1_IN_ROOM", beds_count=1)
    bed = factory.create_bed(room, 1, status="RESERVED")

    user = factory.create_user("report-admin-2@example.com")
    tenant = factory.create_tenant("Report Tenant C", status="prospect")
    invoice = factory.create_invoice(tenant, user=user, reserved_bed=bed, status="approved", total=Decimal("1800.00"))
    factory.create_reservation(
        bed,
        tenant=tenant,
        invoice=invoice,
        user=user,
        expires_at=factory.now(hours=-5),
    )
    expire_reservations_batch(db_session, now=factory.now(), limit=10)

    tables = get_reporting_tables(
        db_session,
        start_date=factory.now().date(),
        end_date=factory.now().date(),
        currency="GHS",
    )

    assert not any(row["Invoice"] == invoice.invoice_no for row in tables["aging_rows"])
