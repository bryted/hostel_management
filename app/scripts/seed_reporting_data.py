"""Seed reporting data for occupancy and financial reports."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

from dotenv import load_dotenv
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.db import get_engine
from app.models import (
    Allocation,
    Bed,
    BedEvent,
    BedReservation,
    Block,
    Floor,
    Invoice,
    Payment,
    Receipt,
    Room,
    Tenant,
    User,
)

load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed report-friendly sample data.")
    parser.add_argument("--apply", action="store_true", help="Apply changes to the database")
    return parser.parse_args()


def get_admin_user_id(session: Session) -> int | None:
    user = (
        session.execute(select(User).where(User.is_admin.is_(True)).order_by(User.created_at))
        .scalars()
        .first()
    )
    return user.id if user else None


def get_or_create_block(session: Session, name: str) -> Block:
    block = session.execute(select(Block).where(Block.name == name)).scalar_one_or_none()
    if block:
        return block
    block = Block(name=name, is_active=True)
    session.add(block)
    session.flush()
    return block


def get_or_create_floor(session: Session, block: Block, label: str) -> Floor:
    floor = (
        session.execute(
            select(Floor).where(Floor.block_id == block.id, Floor.floor_label == label)
        )
        .scalars()
        .first()
    )
    if floor:
        return floor
    floor = Floor(block_id=block.id, floor_label=label, is_active=True)
    session.add(floor)
    session.flush()
    return floor


def get_or_create_room(session: Session, block: Block, floor: Floor, code: str) -> Room:
    room = (
        session.execute(
            select(Room).where(Room.block_id == block.id, Room.room_code == code)
        )
        .scalars()
        .first()
    )
    if room:
        return room
    room = Room(
        block_id=block.id,
        floor_id=floor.id,
        room_code=code,
        room_type="Standard",
        beds_count=4,
        unit_price_per_bed=Decimal("1200"),
        is_active=True,
    )
    session.add(room)
    session.flush()
    return room


def ensure_beds(session: Session, room: Room, count: int) -> list[Bed]:
    existing = (
        session.execute(
            select(Bed).where(Bed.room_id == room.id).order_by(Bed.bed_number)
        )
        .scalars()
        .all()
    )
    by_number = {bed.bed_number: bed for bed in existing}
    for number in range(1, count + 1):
        if number in by_number:
            continue
        bed = Bed(
            room_id=room.id,
            bed_number=number,
            bed_label=f"Bed {number}",
            status="AVAILABLE",
        )
        session.add(bed)
        session.flush()
        by_number[number] = bed
    return [by_number[number] for number in sorted(by_number)]


def set_bed_status(session: Session, bed: Bed, status: str, user_id: int | None) -> None:
    if bed.status == status:
        return
    bed.status = status
    session.add(
        BedEvent(
            bed_id=bed.id,
            event_type="SEED_BED_STATUS",
            user_id=user_id,
            invoice_id=None,
            tenant_id=None,
            detail_json={"status": status},
        )
    )


def get_or_create_tenant(session: Session, name: str) -> Tenant:
    tenant = session.execute(select(Tenant).where(Tenant.name == name)).scalar_one_or_none()
    if tenant:
        return tenant
    phone = "233550000001"
    tenant = Tenant(
        name=name,
        email="demo-tenant@example.com",
        phone=phone,
        normalized_phone=phone,
    )
    session.add(tenant)
    session.flush()
    return tenant


def get_or_create_invoice(
    session: Session,
    tenant: Tenant,
    status: str,
    total: Decimal,
    notes: str,
) -> Invoice:
    invoice = (
        session.execute(
            select(Invoice).where(Invoice.tenant_id == tenant.id, Invoice.notes == notes)
        )
        .scalars()
        .first()
    )
    if invoice:
        return invoice
    now = datetime.now(timezone.utc)
    invoice = Invoice(
        tenant_id=tenant.id,
        user_id=None,
        status=status,
        currency="GHS",
        subtotal=total,
        tax=Decimal("0"),
        total=total,
        issued_at=now,
        due_at=now + timedelta(days=30),
        notes=notes,
        billing_year=now.year,
    )
    session.add(invoice)
    session.flush()
    return invoice


def ensure_payment_and_receipt(
    session: Session,
    tenant: Tenant,
    invoice: Invoice,
    amount: Decimal,
) -> None:
    existing = (
        session.execute(
            select(Payment).where(Payment.invoice_id == invoice.id, Payment.status != "voided")
        )
        .scalars()
        .all()
    )
    total_paid = sum(Decimal(str(p.amount)) for p in existing)
    if total_paid >= amount:
        return
    now = datetime.now(timezone.utc)
    payment = Payment(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        amount=amount - total_paid,
        currency="GHS",
        method="cash",
        status="completed",
        paid_at=now,
    )
    session.add(payment)
    session.flush()
    receipt = Receipt(
        tenant_id=tenant.id,
        payment_id=payment.id,
        amount=payment.amount,
        currency="GHS",
        issued_at=now,
    )
    session.add(receipt)


def seed(apply: bool) -> None:
    engine = get_engine()
    with Session(engine) as session:
        user_id = get_admin_user_id(session)

        block = get_or_create_block(session, "Demo Block A")
        floor = get_or_create_floor(session, block, "Floor 1")
        room = get_or_create_room(session, block, floor, "A-101")
        beds = ensure_beds(session, room, 4)

        tenant = get_or_create_tenant(session, "Demo Tenant")

        invoice_partial = get_or_create_invoice(
            session,
            tenant,
            "partially_paid",
            Decimal("3000"),
            "Seed invoice - partial",
        )
        invoice_paid = get_or_create_invoice(
            session,
            tenant,
            "paid",
            Decimal("2400"),
            "Seed invoice - paid",
        )

        ensure_payment_and_receipt(session, tenant, invoice_partial, Decimal("1500"))
        ensure_payment_and_receipt(session, tenant, invoice_paid, Decimal("2400"))

        bed1, bed2, bed3, bed4 = beds[:4]
        set_bed_status(session, bed1, "AVAILABLE", user_id)
        set_bed_status(session, bed2, "RESERVED", user_id)
        set_bed_status(session, bed3, "OCCUPIED", user_id)
        set_bed_status(session, bed4, "OUT_OF_SERVICE", user_id)

        now = datetime.now(timezone.utc)

        active_reservation = (
            session.execute(
                select(BedReservation)
                .where(BedReservation.bed_id == bed2.id, BedReservation.status == "ACTIVE")
            )
            .scalars()
            .first()
        )
        if not active_reservation:
            session.add(
                BedReservation(
                    bed_id=bed2.id,
                    tenant_id=tenant.id,
                    invoice_id=invoice_partial.id,
                    status="ACTIVE",
                    reserved_at=now - timedelta(days=1),
                    expires_at=now + timedelta(days=2),
                    reserved_by=user_id,
                )
            )

        expired_reservation = (
            session.execute(
                select(BedReservation)
                .where(BedReservation.bed_id == bed1.id, BedReservation.status == "EXPIRED")
            )
            .scalars()
            .first()
        )
        if not expired_reservation:
            session.add(
                BedReservation(
                    bed_id=bed1.id,
                    tenant_id=tenant.id,
                    invoice_id=invoice_partial.id,
                    status="EXPIRED",
                    reserved_at=now - timedelta(days=10),
                    expires_at=now - timedelta(days=5),
                    reserved_by=user_id,
                    cancelled_at=now - timedelta(days=5),
                    cancelled_by=user_id,
                    cancel_reason="Expired (seed)",
                )
            )

        allocation = (
            session.execute(
                select(Allocation)
                .where(Allocation.bed_id == bed3.id, Allocation.status == "CONFIRMED")
            )
            .scalars()
            .first()
        )
        if not allocation:
            session.add(
                Allocation(
                    bed_id=bed3.id,
                    tenant_id=tenant.id,
                    invoice_id=invoice_paid.id,
                    status="CONFIRMED",
                    start_date=now - timedelta(days=30),
                )
            )

        if apply:
            session.commit()
            print("Seed data applied.")
        else:
            session.rollback()
            print("Dry run only. Use --apply to save changes.")


if __name__ == "__main__":
    args = parse_args()
    seed(args.apply)
