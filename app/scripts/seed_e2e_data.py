from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Bed, Block, Floor, Invoice, Payment, Receipt, Room, Tenant, User
from app.services.auth import hash_password
from app.services.invoicing import cancel_invoice, create_invoice, record_payment
from app.services.settings import get_or_create_notification_settings


def _get_or_create_user(
    session: Session,
    *,
    email: str,
    full_name: str,
    is_admin: bool,
    password: str,
) -> User:
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            is_admin=is_admin,
            is_active=True,
            tenant_id=None,
        )
        session.add(user)
        session.flush()
    else:
        user.full_name = full_name
        user.is_admin = is_admin
        user.is_active = True
        user.password_hash = hash_password(password)
    return user


def _get_or_create_room(
    session: Session,
    *,
    room_code: str,
    unit_price_per_bed: Decimal,
    beds_count: int = 2,
    room_type: str = "2_IN_ROOM",
) -> tuple[Room, list[Bed]]:
    block = session.execute(select(Block).where(Block.name == "E2E Block")).scalar_one_or_none()
    if block is None:
        block = Block(name="E2E Block", is_active=True)
        session.add(block)
        session.flush()

    floor = session.execute(
        select(Floor).where(Floor.block_id == block.id, Floor.floor_label == "E2E Level")
    ).scalar_one_or_none()
    if floor is None:
        floor = Floor(block_id=block.id, floor_label="E2E Level", is_active=True)
        session.add(floor)
        session.flush()

    room = session.execute(
        select(Room).where(Room.block_id == block.id, Room.room_code == room_code)
    ).scalar_one_or_none()
    if room is None:
        room = Room(
            block_id=block.id,
            floor_id=floor.id,
            room_code=room_code,
            room_type=room_type,
            beds_count=beds_count,
            unit_price_per_bed=unit_price_per_bed,
            is_active=True,
        )
        session.add(room)
        session.flush()
    else:
        room.room_type = room_type
        room.beds_count = beds_count
        room.unit_price_per_bed = unit_price_per_bed
        room.is_active = True

    beds = session.execute(
        select(Bed).where(Bed.room_id == room.id).order_by(Bed.bed_number.asc())
    ).scalars().all()
    if len(beds) < beds_count:
        for bed_number in range(len(beds) + 1, beds_count + 1):
            bed = Bed(
                room_id=room.id,
                bed_number=bed_number,
                bed_label=f"B{bed_number}",
                status="AVAILABLE",
            )
            session.add(bed)
            session.flush()
            beds.append(bed)
    return room, beds


def _get_or_create_tenant(session: Session, *, name: str, status: str) -> Tenant:
    tenant = session.execute(select(Tenant).where(Tenant.name == name)).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(name=name, status=status)
        session.add(tenant)
        session.flush()
    else:
        tenant.status = status
    return tenant


def _cleanup_browser_billing_artifacts(session: Session, *, user_id: int) -> None:
    now = datetime.now(timezone.utc)
    browser_tenants = session.execute(
        select(Tenant).where(Tenant.name.like("E2E Billing %"))
    ).scalars().all()
    for tenant in browser_tenants:
        invoices = session.execute(
            select(Invoice)
            .where(Invoice.tenant_id == tenant.id)
            .order_by(Invoice.created_at.desc())
        ).scalars().all()
        for invoice in invoices:
            if invoice.status in {"paid", "cancelled"}:
                continue
            cancel_invoice(
                session,
                invoice=invoice,
                user_id=user_id,
                reason="Reset E2E browser billing artifacts",
                now=now,
            )


def _cancel_open_invoices_for_tenant(session: Session, *, tenant_id: int, user_id: int, reason: str) -> None:
    now = datetime.now(timezone.utc)
    invoices = session.execute(
        select(Invoice).where(Invoice.tenant_id == tenant_id).order_by(Invoice.created_at.desc())
    ).scalars().all()
    for invoice in invoices:
        if invoice.status not in {"draft", "submitted", "approved"}:
            continue
        cancel_invoice(
            session,
            invoice=invoice,
            user_id=user_id,
            reason=reason,
            now=now,
        )


def seed() -> None:
    engine = get_engine()
    with Session(engine) as session:
        admin = _get_or_create_user(
            session,
            email="e2e-admin@example.com",
            full_name="E2E Admin",
            is_admin=True,
            password="StrongPass1!",
        )
        _get_or_create_user(
            session,
            email="user@example.com",
            full_name="Cashier User",
            is_admin=False,
            password="UserPass1!",
        )
        settings = get_or_create_notification_settings(session)
        settings.mock_mode = True
        settings.auto_approve_invoices = True
        settings.block_duplicate_payment_reference = True
        settings.reservation_default_hold_hours = 24

        _cleanup_browser_billing_artifacts(session, user_id=int(admin.id))

        _primary_room, primary_beds = _get_or_create_room(
            session,
            room_code="E2E-101",
            unit_price_per_bed=Decimal("950.00"),
        )
        _warning_room, warning_beds = _get_or_create_room(
            session,
            room_code="E2E-102",
            unit_price_per_bed=Decimal("975.00"),
        )
        _source_room, source_beds = _get_or_create_room(
            session,
            room_code="E2E-103",
            unit_price_per_bed=Decimal("925.00"),
            beds_count=1,
            room_type="1_IN_ROOM",
        )
        available_bed = primary_beds[0]
        resident_bed = primary_beds[1]
        hold_warning_bed = warning_beds[0]
        duplicate_target_bed = warning_beds[1]
        duplicate_source_bed = source_beds[0]
        for bed in [available_bed, resident_bed, hold_warning_bed, duplicate_target_bed, duplicate_source_bed]:
            bed.status = "AVAILABLE"

        prospect = _get_or_create_tenant(session, name="E2E Prospect", status="prospect")
        resident = _get_or_create_tenant(session, name="E2E Resident", status="active")
        hold_warning_tenant = _get_or_create_tenant(session, name="E2E Hold Warning", status="prospect")
        duplicate_source_tenant = _get_or_create_tenant(session, name="E2E Duplicate Source", status="active")
        duplicate_target_tenant = _get_or_create_tenant(session, name="E2E Duplicate Target", status="prospect")

        existing_invoice = session.execute(
            select(Invoice).where(Invoice.tenant_id == resident.id).order_by(Invoice.created_at.desc())
        ).scalars().first()
        if existing_invoice is None:
            now = datetime.now(timezone.utc)
            invoice = create_invoice(
                session,
                tenant_id=int(resident.id),
                user_id=int(admin.id),
                reserved_bed_id=int(resident_bed.id),
                currency="GHS",
                tax=Decimal("0"),
                discount=Decimal("0"),
                notes="Seeded receipt workflow",
                status="approved",
                due_at=now + timedelta(days=7),
                hold_until=now + timedelta(hours=24),
                now=now,
            )
            payment, receipt, _ = record_payment(
                session,
                invoice=invoice,
                user_id=int(admin.id),
                amount=Decimal(str(invoice.total)),
                method="cash",
                reference=None,
                now=now,
            )
            session.flush()
            if receipt is None:
                raise RuntimeError("Failed to create seeded receipt.")
        else:
            receipts = session.execute(
                select(Receipt).where(Receipt.tenant_id == resident.id)
            ).scalars().all()
            if not receipts:
                now = datetime.now(timezone.utc)
                _payment, _receipt, _ = record_payment(
                    session,
                    invoice=existing_invoice,
                    user_id=int(admin.id),
                    amount=Decimal(str(existing_invoice.total)),
                    method="cash",
                    reference=None,
                    now=now,
                )

        _cancel_open_invoices_for_tenant(
            session,
            tenant_id=int(hold_warning_tenant.id),
            user_id=int(admin.id),
            reason="Reset E2E hold warning invoice",
        )
        _cancel_open_invoices_for_tenant(
            session,
            tenant_id=int(duplicate_target_tenant.id),
            user_id=int(admin.id),
            reason="Reset E2E duplicate target invoice",
        )
        _cancel_open_invoices_for_tenant(
            session,
            tenant_id=int(duplicate_source_tenant.id),
            user_id=int(admin.id),
            reason="Reset E2E duplicate source invoice",
        )

        now = datetime.now(timezone.utc)
        create_invoice(
            session,
            tenant_id=int(hold_warning_tenant.id),
            user_id=int(admin.id),
            reserved_bed_id=int(hold_warning_bed.id),
            currency="GHS",
            tax=Decimal("0"),
            discount=Decimal("0"),
            notes="Seeded short hold warning workflow",
            status="approved",
            due_at=now + timedelta(days=1),
            hold_until=now + timedelta(hours=4),
            now=now,
        )

        create_invoice(
            session,
            tenant_id=int(duplicate_target_tenant.id),
            user_id=int(admin.id),
            reserved_bed_id=int(duplicate_target_bed.id),
            currency="GHS",
            tax=Decimal("0"),
            discount=Decimal("0"),
            notes="Seeded duplicate reference warning target",
            status="approved",
            due_at=now + timedelta(days=1),
            hold_until=now + timedelta(hours=24),
            now=now,
        )

        duplicate_reference = "E2E-DUP-REF"
        has_duplicate_reference = session.execute(
            select(Payment.id).where(Payment.reference == duplicate_reference).limit(1)
        ).scalar_one_or_none()
        if has_duplicate_reference is None:
            source_invoice = create_invoice(
                session,
                tenant_id=int(duplicate_source_tenant.id),
                user_id=int(admin.id),
                reserved_bed_id=int(duplicate_source_bed.id),
                currency="GHS",
                tax=Decimal("0"),
                discount=Decimal("0"),
                notes="Seeded duplicate reference source",
                status="approved",
                due_at=now + timedelta(days=1),
                hold_until=now + timedelta(hours=24),
                now=now,
            )
            record_payment(
                session,
                invoice=source_invoice,
                user_id=int(admin.id),
                amount=Decimal(str(source_invoice.total)),
                method="card",
                reference=duplicate_reference,
                now=now,
            )

        session.commit()
        print("Seeded E2E data.")
        print("Admin: e2e-admin@example.com / StrongPass1!")
        print("Cashier: user@example.com / UserPass1!")
        print(f"Prospect tenant: {prospect.name}")
        print("Resident tenant: E2E Resident")


if __name__ == "__main__":
    seed()
