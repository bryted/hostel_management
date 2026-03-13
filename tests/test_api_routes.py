from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Invoice, NotificationOutbox, NotificationSettings, Receipt, User
from app.services.auth import hash_password
from app.services.reservations import expire_reservations_batch
from backend.hostel_api.config import settings
from backend.hostel_api.deps import get_db_session
from backend.hostel_api.main import app
from backend.hostel_api.security import login_attempt_limiter


def _build_client(db_session):
    def override_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    return TestClient(app)


def test_auth_login_me_and_logout(factory, db_session):
    user = factory.create_user(full_name="Admin User", is_admin=True)
    user.password_hash = hash_password("StrongPass1!")
    db_session.flush()

    try:
        with _build_client(db_session) as client:
            unauthorized = client.get("/api/v1/auth/me")
            assert unauthorized.status_code == 401

            login = client.post(
                "/api/v1/auth/login",
                json={"username": user.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200
            assert login.json()["email"] == user.email

            me = client.get("/api/v1/auth/me")
            assert me.status_code == 200
            assert me.json()["full_name"] == "Admin User"

            logout = client.post("/api/v1/auth/logout")
            assert logout.status_code == 200

            after_logout = client.get("/api/v1/auth/me")
            assert after_logout.status_code == 401
    finally:
        app.dependency_overrides.clear()
        login_attempt_limiter.reset(f"testclient:{user.email}")


def test_workspace_and_transfer_endpoint(factory, db_session):
    admin = factory.create_user(full_name="Ops Admin", is_admin=True)
    admin.password_hash = hash_password("StrongPass1!")
    block = factory.create_block("Alpha")
    floor = factory.create_floor(block, "Floor 1")
    room = factory.create_room(block, floor, room_code="A-101", room_type="2_IN_ROOM", beds_count=2)
    old_bed = factory.create_bed(room, 1, status="OCCUPIED")
    new_bed = factory.create_bed(room, 2, status="AVAILABLE")
    tenant = factory.create_tenant("Resident One", status="active")
    invoice = factory.create_invoice(tenant, user=admin, reserved_bed=old_bed, total=Decimal("1200.00"))
    factory.create_payment(tenant, invoice, Decimal("1200.00"), user=admin)
    allocation = factory.create_allocation(old_bed, tenant=tenant, invoice=invoice, user=admin)
    db_session.flush()

    try:
        with _build_client(db_session) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": admin.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200

            workspace = client.get(f"/api/v1/tenants/{tenant.id}/workspace")
            assert workspace.status_code == 200
            payload = workspace.json()
            assert payload["tenant"]["name"] == "Resident One"
            assert payload["active_allocation"]["bed_id"] == old_bed.id
            assert payload["available_beds"][0]["bed_id"] == new_bed.id

            transfer = client.post(
                f"/api/v1/allocations/{allocation.id}/transfer",
                json={"new_bed_id": new_bed.id, "reason": "Room rebalance"},
            )
            assert transfer.status_code == 200
            assert transfer.json()["bed_id"] == new_bed.id

            refreshed = client.get(f"/api/v1/tenants/{tenant.id}/workspace")
            assert refreshed.status_code == 200
            refreshed_payload = refreshed.json()
            assert refreshed_payload["active_allocation"]["bed_id"] == new_bed.id
    finally:
        app.dependency_overrides.clear()


def test_billing_and_onboarding_endpoints(factory, db_session):
    admin = factory.create_user(full_name="Queue Admin", is_admin=True)
    admin.password_hash = hash_password("StrongPass1!")
    block = factory.create_block("Queue Block")
    floor = factory.create_floor(block, "Floor 1")
    room = factory.create_room(block, floor, room_code="Q-101", room_type="2_IN_ROOM", beds_count=2)
    bed = factory.create_bed(room, 1, status="AVAILABLE")
    tenant = factory.create_tenant("Queue Prospect", status="prospect")
    invoice = factory.create_invoice(tenant, user=admin, reserved_bed=bed, status="approved", total=Decimal("900.00"))
    payment = factory.create_payment(tenant, invoice, Decimal("300.00"), user=admin)
    db_session.add(
        Receipt(
            tenant_id=tenant.id,
            payment_id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            issued_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()

    try:
        with _build_client(db_session) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": admin.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200

            billing = client.get("/api/v1/billing/overview")
            assert billing.status_code == 200
            billing_payload = billing.json()
            assert any(row["invoice_no"] == invoice.invoice_no for row in billing_payload["invoice_rows"])
            assert any(row["payment_no"] == payment.payment_no for row in billing_payload["payment_rows"])
            assert any(row["payment_no"] == payment.payment_no for row in billing_payload["receipt_rows"])

            onboarding = client.get("/api/v1/onboarding/queue")
            assert onboarding.status_code == 200
            onboarding_payload = onboarding.json()
            assert onboarding_payload["approved_unpaid"] >= 0
            assert any(row["invoice_no"] == invoice.invoice_no for row in onboarding_payload["queue_rows"])
    finally:
        app.dependency_overrides.clear()


def test_invoice_create_payment_and_receipt_routes(factory, db_session):
    admin = factory.create_user(full_name="Billing Admin", is_admin=True)
    admin.password_hash = hash_password("StrongPass1!")
    block = factory.create_block("Billing Block")
    floor = factory.create_floor(block, "Floor 1")
    room = factory.create_room(
        block,
        floor,
        room_code="B-101",
        room_type="2_IN_ROOM",
        beds_count=2,
        unit_price_per_bed=Decimal("1500.00"),
    )
    bed = factory.create_bed(room, 1, status="AVAILABLE")
    tenant = factory.create_tenant("Billing Prospect", status="prospect")
    db_session.flush()

    try:
        with _build_client(db_session) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": admin.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200

            created = client.post(
                "/api/v1/invoices",
                json={
                    "tenant_id": tenant.id,
                    "reserved_bed_id": bed.id,
                    "tax": 0,
                    "discount": 0,
                    "hold_hours": 24,
                    "due_at": factory.now().date().isoformat(),
                    "notes": "New web invoice",
                    "submit_now": True,
                },
            )
            assert created.status_code == 200
            invoice_id = created.json()["invoice_id"]
            assert invoice_id is not None

            invoice = db_session.get(Invoice, invoice_id)
            assert invoice is not None
            if invoice.status == "submitted":
                approved = client.post(f"/api/v1/invoices/{invoice_id}/approve", json={})
                assert approved.status_code == 200
            else:
                assert invoice.status == "approved"

            paid = client.post(
                f"/api/v1/invoices/{invoice_id}/payments",
                json={"amount": 500, "method": "mobile_money", "reference": "MM-123"},
            )
            assert paid.status_code == 200
            payload = paid.json()
            assert payload["receipt_id"] is not None

            detail = client.get(f"/api/v1/invoices/{invoice_id}")
            assert detail.status_code == 200
            detail_payload = detail.json()
            assert detail_payload["invoice"]["invoice_no"]
            assert detail_payload["payments"][0]["reference"] == "MM-123"

            receipt_id = payload["receipt_id"]
            receipt = client.get(f"/api/v1/receipts/{receipt_id}")
            assert receipt.status_code == 200
            assert receipt.json()["receipt"]["receipt_no"]

            printed = client.post(f"/api/v1/receipts/{receipt_id}/print", json={})
            assert printed.status_code == 200

            pdf = client.get(f"/api/v1/receipts/{receipt_id}/pdf")
            assert pdf.status_code == 200
            assert pdf.headers["content-type"] == "application/pdf"
    finally:
        app.dependency_overrides.clear()


def test_submitted_invoice_with_expired_hold_requires_new_bed_before_approval(factory, db_session):
    admin = factory.create_user(full_name="Approval Admin", is_admin=True)
    admin.password_hash = hash_password("StrongPass1!")
    block = factory.create_block("Approval Block")
    floor = factory.create_floor(block, "Level 1")
    room = factory.create_room(
        block,
        floor,
        room_code="APR-101",
        room_type="1_IN_ROOM",
        beds_count=1,
        unit_price_per_bed=Decimal("1500.00"),
    )
    bed = factory.create_bed(room, 1, status="RESERVED")
    tenant = factory.create_tenant("Approval Tenant", status="prospect")
    invoice = factory.create_invoice(tenant, user=admin, reserved_bed=bed, status="submitted", total=Decimal("1500.00"))
    factory.create_reservation(
        bed,
        tenant=tenant,
        invoice=invoice,
        user=admin,
        expires_at=factory.now(hours=-4),
    )
    expire_reservations_batch(db_session, now=factory.now(), limit=20)
    db_session.commit()

    try:
        with _build_client(db_session) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": admin.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200

            approved = client.post(f"/api/v1/invoices/{invoice.id}/approve", json={})
            assert approved.status_code == 400
            assert "Select a new bed before approval" in approved.json()["detail"]

            detail = client.get(f"/api/v1/invoices/{invoice.id}")
            assert detail.status_code == 200
            assert detail.json()["hold_expired"] is True
            assert detail.json()["reserved_bed_id"] is None
    finally:
        app.dependency_overrides.clear()


def test_receipt_verify_and_sms_routes(factory, db_session, monkeypatch):
    monkeypatch.setenv("NOTIFICATIONS_MOCK", "1")
    admin = factory.create_user(full_name="Receipt Admin", is_admin=True)
    admin.password_hash = hash_password("StrongPass1!")
    tenant = factory.create_tenant("Receipt Tenant", status="active")
    tenant.phone = "2335550101"
    tenant.normalized_phone = "2335550101"
    invoice = factory.create_invoice(tenant, user=admin, total=Decimal("850.00"))
    payment = factory.create_payment(tenant, invoice, Decimal("850.00"), user=admin)
    receipt = Receipt(
        tenant_id=tenant.id,
        payment_id=payment.id,
        receipt_no="REC-VERIFY-0001",
        amount=payment.amount,
        currency=payment.currency,
        issued_at=datetime.now(timezone.utc),
    )
    db_session.add(receipt)
    db_session.flush()

    try:
        with _build_client(db_session) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": admin.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200

            detail = client.get(f"/api/v1/receipts/{receipt.id}")
            assert detail.status_code == 200
            detail_payload = detail.json()
            assert detail_payload["verification_code"]
            assert detail_payload["verification_url"].endswith(detail_payload["verification_code"])
            assert detail_payload["sms_available"] is True

            verified = client.get(
                "/api/v1/receipts/verify",
                params={
                    "receipt_no": detail_payload["receipt"]["receipt_no"],
                    "code": detail_payload["verification_code"],
                },
            )
            assert verified.status_code == 200
            assert verified.json()["valid"] is True

            sms = client.post(f"/api/v1/receipts/{receipt.id}/send-sms", json={})
            assert sms.status_code == 200
            assert sms.json()["message"] == "Receipt SMS sent."
    finally:
        app.dependency_overrides.clear()
        monkeypatch.delenv("NOTIFICATIONS_MOCK", raising=False)


def test_inventory_overview_and_admin_mutations(factory, db_session):
    admin = factory.create_user(full_name="Inventory Admin", is_admin=True)
    admin.password_hash = hash_password("StrongPass1!")
    block = factory.create_block("Inventory Block")
    floor = factory.create_floor(block, "Level 1")
    factory.create_room(
        block,
        floor,
        room_code="I-101",
        room_type="2_IN_ROOM",
        beds_count=2,
        unit_price_per_bed=Decimal("1800.00"),
    )
    db_session.flush()

    try:
        with _build_client(db_session) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": admin.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200

            overview = client.get("/api/v1/inventory/overview")
            assert overview.status_code == 200
            payload = overview.json()
            assert payload["total_blocks"] >= 1
            assert any(room["room_code"] == "I-101" for room in payload["rooms"])
            assert "integrity_rows" in payload

            created_block = client.post("/api/v1/inventory/blocks", json={"name": "North Wing"})
            assert created_block.status_code == 200

            created_floor = client.post(
                "/api/v1/inventory/floors",
                json={"block_id": block.id, "floor_label": "Level 2"},
            )
            assert created_floor.status_code == 200

            created_room = client.post(
                "/api/v1/inventory/rooms",
                json={
                    "block_id": block.id,
                    "floor_id": floor.id,
                    "room_code": "I-102",
                    "room_type": "3_IN_ROOM",
                    "unit_price_per_bed": 2000,
                    "is_active": True,
                },
            )
            assert created_room.status_code == 200

            upload = client.post(
                "/api/v1/inventory/upload",
                files={
                    "file": (
                        "inventory.csv",
                        "block,floor,room_code,room_type,unit_price_per_bed\nInventory Block,Level 1,I-103,2_IN_ROOM,1500\n",
                        "text/csv",
                    )
                },
            )
            assert upload.status_code == 200
            assert "Created rooms" in upload.json()["message"]
    finally:
        app.dependency_overrides.clear()


def test_inventory_requires_admin(factory, db_session):
    cashier = factory.create_user(full_name="Cashier User", is_admin=False)
    cashier.password_hash = hash_password("StrongPass1!")
    db_session.flush()

    try:
        with _build_client(db_session) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": cashier.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200

            overview = client.get("/api/v1/inventory/overview")
            assert overview.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_allocations_reports_and_settings_routes(factory, db_session):
    admin = factory.create_user(full_name="Platform Admin", is_admin=True)
    admin.password_hash = hash_password("StrongPass1!")
    block = factory.create_block("Ops Block")
    floor = factory.create_floor(block, "Floor 1")
    room = factory.create_room(
        block,
        floor,
        room_code="O-101",
        room_type="2_IN_ROOM",
        beds_count=2,
        unit_price_per_bed=Decimal("1400.00"),
    )
    occupied_bed = factory.create_bed(room, 1, status="OCCUPIED")
    available_bed = factory.create_bed(room, 2, status="AVAILABLE")
    tenant = factory.create_tenant("Resident Admin", status="active")
    invoice = factory.create_invoice(
        tenant,
        user=admin,
        reserved_bed=occupied_bed,
        status="approved",
        total=Decimal("1400.00"),
    )
    factory.create_payment(tenant, invoice, Decimal("1400.00"), user=admin)
    factory.create_allocation(occupied_bed, tenant=tenant, invoice=invoice, user=admin)
    db_session.add(
        NotificationSettings(
            block_duplicate_payment_reference=True,
            notification_max_attempts=4,
            notification_retry_delay_seconds=600,
            reservation_default_hold_hours=36,
        )
    )
    db_session.flush()

    try:
        with _build_client(db_session) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": admin.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200

            allocations = client.get("/api/v1/allocations/overview")
            assert allocations.status_code == 200
            allocation_payload = allocations.json()
            assert allocation_payload["active_allocations"] >= 1
            matching_row = next(
                row for row in allocation_payload["rows"] if row["tenant_name"] == "Resident Admin"
            )
            transfer_target_ids = [target["bed_id"] for target in matching_row["transfer_targets"]]
            assert available_bed.id in transfer_target_ids

            reports = client.get("/api/v1/reports/overview")
            assert reports.status_code == 200
            report_payload = reports.json()
            assert report_payload["collected_today"]
            assert "room_utilization" in report_payload

            settings = client.get("/api/v1/settings/overview")
            assert settings.status_code == 200
            settings_payload = settings.json()
            assert settings_payload["settings"]["reservation_default_hold_hours"] >= 1
            assert any(account["email"] == admin.email for account in settings_payload["users"])

            updated = client.post(
                "/api/v1/settings/guardrails",
                json={
                    "block_duplicate_payment_reference": False,
                    "notification_max_attempts": 5,
                    "notification_retry_delay_seconds": 900,
                    "reservation_default_hold_hours": 48,
                    "auto_approve_invoices": False,
                },
            )
            assert updated.status_code == 200

            created_user = client.post(
                "/api/v1/settings/users",
                json={
                    "email": "cashdesk@example.com",
                    "full_name": "Cash Desk",
                    "password": "StrongPass1!",
                    "is_admin": False,
                },
            )
            assert created_user.status_code == 200

            persisted = db_session.execute(
                select(User).where(User.email == "cashdesk@example.com")
            ).scalar_one_or_none()
            assert persisted is not None
            assert bool(persisted.is_admin) is False
    finally:
        app.dependency_overrides.clear()


def test_login_rate_limit(factory, db_session):
    user = factory.create_user(full_name="Rate Limited", is_admin=False)
    user.password_hash = hash_password("StrongPass1!")
    db_session.flush()

    old_attempts = settings.login_max_attempts
    old_window = settings.login_window_seconds
    old_lockout = settings.login_lockout_seconds
    settings.login_max_attempts = 2
    settings.login_window_seconds = 600
    settings.login_lockout_seconds = 600

    try:
        with _build_client(db_session) as client:
            first = client.post(
                "/api/v1/auth/login",
                json={"username": user.email, "password": "WrongPass1!"},
            )
            assert first.status_code == 401

            second = client.post(
                "/api/v1/auth/login",
                json={"username": user.email, "password": "WrongPass1!"},
            )
            assert second.status_code == 429

            blocked = client.post(
                "/api/v1/auth/login",
                json={"username": user.email, "password": "StrongPass1!"},
            )
            assert blocked.status_code == 429
    finally:
        settings.login_max_attempts = old_attempts
        settings.login_window_seconds = old_window
        settings.login_lockout_seconds = old_lockout
        login_attempt_limiter.reset(f"testclient:{user.email}")
        app.dependency_overrides.clear()


def test_settings_provider_updates_and_user_admin_flows(factory, db_session, monkeypatch):
    monkeypatch.setenv("NOTIFICATIONS_MOCK", "1")
    admin = factory.create_user(full_name="Settings Admin", is_admin=True)
    admin.password_hash = hash_password("StrongPass1!")
    cashier = factory.create_user(full_name="Settings Cashier", is_admin=False)
    cashier.password_hash = hash_password("StrongPass1!")
    db_session.flush()

    try:
        with _build_client(db_session) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": admin.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200

            guardrails = client.post(
                "/api/v1/settings/guardrails",
                json={
                    "block_duplicate_payment_reference": True,
                    "notification_max_attempts": 6,
                    "notification_retry_delay_seconds": 120,
                    "reservation_default_hold_hours": 12,
                    "auto_approve_invoices": True,
                },
            )
            assert guardrails.status_code == 200

            providers = client.post(
                "/api/v1/settings/providers",
                json={
                    "mock_mode": True,
                    "sms_api_url": "https://sms.example.test/send",
                    "sms_api_key": "sms-secret",
                    "sms_sender_id": "HOSTEL",
                    "smtp_host": "smtp.example.test",
                    "smtp_port": 587,
                    "smtp_user": "mailer@example.test",
                    "smtp_password": "smtp-secret",
                    "smtp_from": "ops@example.test",
                    "whatsapp_access_token": "wa-secret",
                    "whatsapp_phone_number_id": "12345",
                    "whatsapp_api_version": "v19.0",
                },
            )
            assert providers.status_code == 200

            test_email = client.post(
                "/api/v1/settings/providers/test",
                json={"channel": "email", "recipient": "qa@example.test"},
            )
            assert test_email.status_code == 200

            test_sms = client.post(
                "/api/v1/settings/providers/test",
                json={"channel": "sms", "recipient": "233555000111"},
            )
            assert test_sms.status_code == 200

            user_update = client.post(
                f"/api/v1/settings/users/{cashier.id}",
                json={"is_active": False, "is_admin": True},
            )
            assert user_update.status_code == 200

            reset_password = client.post(
                f"/api/v1/settings/users/{cashier.id}/reset-password",
                json={"password": "ChangedPass1!"},
            )
            assert reset_password.status_code == 200

            overview = client.get("/api/v1/settings/overview")
            assert overview.status_code == 200
            payload = overview.json()
            assert payload["settings"]["auto_approve_invoices"] is True
            assert payload["settings"]["mock_mode"] is True
            assert payload["settings"]["sms_api_key_set"] is True
            assert payload["settings"]["smtp_password_set"] is True
            assert payload["settings"]["whatsapp_access_token_set"] is True
            assert payload["worker_status"]["interval_minutes"] >= 1
            assert "Billing" in payload["cashier_scope"]
            assert isinstance(payload["queue_statuses"], list)

            persisted = db_session.get(User, cashier.id)
            assert persisted is not None
            assert bool(persisted.is_active) is False
            assert bool(persisted.is_admin) is True
    finally:
        app.dependency_overrides.clear()
        monkeypatch.delenv("NOTIFICATIONS_MOCK", raising=False)


def test_password_reset_request_confirm_and_login(factory, db_session, monkeypatch):
    monkeypatch.setenv("NOTIFICATIONS_MOCK", "1")
    user = factory.create_user(full_name="Reset User", is_admin=False)
    user.password_hash = hash_password("StrongPass1!")
    db_session.flush()

    try:
        with _build_client(db_session) as client:
            requested = client.post(
                "/api/v1/auth/password-reset/request",
                json={"username": user.email},
            )
            assert requested.status_code == 200
            reset_token = requested.json()["reset_token"]
            assert reset_token

            confirmed = client.post(
                "/api/v1/auth/password-reset/confirm",
                json={"token": reset_token, "password": "ChangedPass1!"},
            )
            assert confirmed.status_code == 200

            login = client.post(
                "/api/v1/auth/login",
                json={"username": user.email, "password": "ChangedPass1!"},
            )
            assert login.status_code == 200
    finally:
        app.dependency_overrides.clear()
        monkeypatch.delenv("NOTIFICATIONS_MOCK", raising=False)


def test_auto_approve_search_and_finance_export(factory, db_session):
    admin = factory.create_user(full_name="Auto Approve", is_admin=True)
    admin.password_hash = hash_password("StrongPass1!")
    cashier = factory.create_user(full_name="Cashier Scope", is_admin=False)
    cashier.password_hash = hash_password("StrongPass1!")
    block = factory.create_block("Search Block")
    floor = factory.create_floor(block, "Level 1")
    room = factory.create_room(
        block,
        floor,
        room_code="S-101",
        room_type="2_IN_ROOM",
        beds_count=2,
        unit_price_per_bed=Decimal("1100.00"),
    )
    bed = factory.create_bed(room, 1, status="AVAILABLE")
    tenant = factory.create_tenant("Search Tenant", status="prospect")
    try:
        with _build_client(db_session) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": admin.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200

            guardrails = client.post(
                "/api/v1/settings/guardrails",
                json={
                    "block_duplicate_payment_reference": False,
                    "notification_max_attempts": 3,
                    "notification_retry_delay_seconds": 300,
                    "reservation_default_hold_hours": 24,
                    "auto_approve_invoices": True,
                },
            )
            assert guardrails.status_code == 200

            created = client.post(
                "/api/v1/invoices",
                json={
                    "tenant_id": tenant.id,
                    "reserved_bed_id": bed.id,
                    "tax": 0,
                    "discount": 0,
                    "hold_hours": 24,
                    "due_at": factory.now().date().isoformat(),
                    "notes": "Auto-approved invoice",
                    "submit_now": True,
                },
            )
            assert created.status_code == 200
            invoice_id = created.json()["invoice_id"]
            invoice = db_session.get(Invoice, invoice_id)
            assert invoice is not None
            assert invoice.status == "approved"

            paid = client.post(
                f"/api/v1/invoices/{invoice_id}/payments",
                json={"amount": 500, "method": "cash", "reference": ""},
            )
            assert paid.status_code == 200
            receipt_id = paid.json()["receipt_id"]
            assert receipt_id is not None

            search = client.get("/api/v1/search", params={"q": "Search Tenant"})
            assert search.status_code == 200
            titles = [row["title"] for row in search.json()["results"]]
            assert "Search Tenant" in titles

            export = client.get("/api/v1/reports/finance-export.csv")
            assert export.status_code == 200
            assert export.headers["content-type"].startswith("text/csv")
            assert "Search Tenant" in export.text

        with _build_client(db_session) as cashier_client:
            login = cashier_client.post(
                "/api/v1/auth/login",
                json={"username": cashier.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200

            onboarding = cashier_client.get("/api/v1/onboarding/queue")
            assert onboarding.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_tenant_crud_and_inventory_lifecycle_routes(factory, db_session):
    admin = factory.create_user(full_name="Tenant Admin", is_admin=True)
    admin.password_hash = hash_password("StrongPass1!")
    block = factory.create_block("Lifecycle Block")
    floor = factory.create_floor(block, "Ground")
    room = factory.create_room(block, floor, room_code="L-101", room_type="2_IN_ROOM", beds_count=2)
    db_session.flush()

    try:
        with _build_client(db_session) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": admin.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200

            created = client.post(
                "/api/v1/tenants",
                json={
                    "name": "Lifecycle Tenant",
                    "email": "tenant.lifecycle@example.com",
                    "phone": "2335551000",
                    "status": "prospect",
                    "room": "Waiting intake",
                },
            )
            assert created.status_code == 200
            tenant_id = created.json()["tenant_id"]
            assert tenant_id is not None

            updated = client.post(
                f"/api/v1/tenants/{tenant_id}",
                json={
                    "name": "Lifecycle Tenant",
                    "email": "tenant.lifecycle@example.com",
                    "phone": "2335551000",
                    "status": "active",
                    "room": "Desk 1",
                },
            )
            assert updated.status_code == 200

            directory = client.get("/api/v1/tenants", params={"search": "Lifecycle Tenant"})
            assert directory.status_code == 200
            assert directory.json()[0]["room"] == "Desk 1"

            block_update = client.post(
                f"/api/v1/inventory/blocks/{block.id}",
                json={"name": "Lifecycle Block Renamed", "is_active": True},
            )
            assert block_update.status_code == 200

            floor_update = client.post(
                f"/api/v1/inventory/floors/{floor.id}",
                json={"floor_label": "Ground Updated", "is_active": True},
            )
            assert floor_update.status_code == 200

            room_update = client.post(
                f"/api/v1/inventory/rooms/{room.id}",
                json={
                    "block_id": block.id,
                    "floor_id": floor.id,
                    "room_code": "L-101",
                    "room_type": "2_IN_ROOM",
                    "unit_price_per_bed": 1250,
                    "is_active": False,
                },
            )
            assert room_update.status_code == 200

            block_disable = client.post(
                f"/api/v1/inventory/blocks/{block.id}",
                json={"name": "Lifecycle Block Renamed", "is_active": False},
            )
            assert block_disable.status_code == 200

            floor_disable = client.post(
                f"/api/v1/inventory/floors/{floor.id}",
                json={"floor_label": "Ground Updated", "is_active": False},
            )
            assert floor_disable.status_code == 200

            archived = client.post(f"/api/v1/tenants/{tenant_id}/archive", json={})
            assert archived.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_invoice_corrections_receipt_channels_and_settings_ops(factory, db_session, monkeypatch):
    monkeypatch.setenv("NOTIFICATIONS_MOCK", "1")
    admin = factory.create_user(full_name="Correction Admin", is_admin=True)
    admin.password_hash = hash_password("StrongPass1!")
    block = factory.create_block("Correction Block")
    floor = factory.create_floor(block, "Level 1")
    room = factory.create_room(block, floor, room_code="C-101", room_type="2_IN_ROOM", beds_count=2)
    bed_one = factory.create_bed(room, 1, status="AVAILABLE")
    bed_two = factory.create_bed(room, 2, status="AVAILABLE")
    tenant = factory.create_tenant("Correction Tenant", status="prospect")
    tenant.email = "correction.tenant@example.com"
    tenant.phone = "2335550001"
    tenant.normalized_phone = "2335550001"
    invoice = factory.create_invoice(tenant, user=admin, reserved_bed=bed_one, status="approved", total=Decimal("1000.00"))
    db_session.flush()

    try:
        with _build_client(db_session) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": admin.email, "password": "StrongPass1!"},
            )
            assert login.status_code == 200

            invoice_update = client.post(
                f"/api/v1/invoices/{invoice.id}/update",
                json={
                    "reserved_bed_id": bed_two.id,
                    "tax": 50,
                    "discount": 10,
                    "hold_hours": 24,
                    "due_at": factory.now().date().isoformat(),
                    "notes": "Adjusted invoice",
                },
            )
            assert invoice_update.status_code == 200

            payment = client.post(
                f"/api/v1/invoices/{invoice.id}/payments",
                json={"amount": 400, "method": "mobile_money", "reference": "MM-CORR-1"},
            )
            assert payment.status_code == 200
            receipt_id = payment.json()["receipt_id"]
            payment_id = payment.json()["payment_id"]
            assert receipt_id is not None
            assert payment_id is not None

            voided = client.post(
                f"/api/v1/invoices/payments/{payment_id}/void",
                json={"reason": "Correction"},
            )
            assert voided.status_code == 200

            receipt_email = client.post(f"/api/v1/receipts/{receipt_id}/send-email", json={})
            assert receipt_email.status_code == 200

            receipt_whatsapp = client.post(f"/api/v1/receipts/{receipt_id}/send-whatsapp", json={})
            assert receipt_whatsapp.status_code == 200

            outbox = NotificationOutbox(
                tenant_id=tenant.id,
                channel="sms",
                recipient="2335550001",
                body="Queued test",
                status="failed",
                attempt_count=2,
                error="Upstream error",
            )
            db_session.add(outbox)
            db_session.flush()

            retry = client.post(f"/api/v1/settings/notifications/{outbox.id}/retry", json={})
            assert retry.status_code == 200

            worker = client.post("/api/v1/settings/workers/reservations/run", json={})
            assert worker.status_code == 200

            cancelled = client.post(
                f"/api/v1/invoices/{invoice.id}/cancel",
                json={"reason": "Start over"},
            )
            assert cancelled.status_code == 200
    finally:
        app.dependency_overrides.clear()
        monkeypatch.delenv("NOTIFICATIONS_MOCK", raising=False)
