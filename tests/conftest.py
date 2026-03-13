from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import Allocation, Bed, BedReservation, Block, Floor, Invoice, Payment, Room, Tenant, User


@pytest.fixture(scope="session")
def database_url() -> str:
    load_dotenv()
    test_url = (os.getenv("TEST_DATABASE_URL") or "").strip()
    if test_url:
        return test_url

    default_url = (os.getenv("DATABASE_URL") or "").strip()
    allow_non_test = (os.getenv("ALLOW_NON_TEST_DB_FOR_TESTS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if default_url and ("test" in default_url.lower() or allow_non_test):
        return default_url

    pytest.skip(
        "TEST_DATABASE_URL is not set. Refusing to run integration tests against a non-test database."
    )


@pytest.fixture(scope="session")
def engine(database_url: str):
    engine = create_engine(database_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(engine) -> Session:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, future=True)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def factory(db_session: Session):
    suffix = uuid.uuid4().hex[:8]
    counters = {"invoice": 0, "payment": 0, "user": 0, "block": 0, "floor": 0, "room": 0, "tenant": 0}

    class Factory:
        @staticmethod
        def now(hours: int = 0) -> datetime:
            return datetime.now(timezone.utc) + timedelta(hours=hours)

        def create_block(self, name: str | None = None) -> Block:
            counters["block"] += 1
            block = Block(name=name or f"Block-{suffix}-{counters['block']}", is_active=True)
            db_session.add(block)
            db_session.flush()
            return block

        def create_floor(self, block: Block, label: str | None = None) -> Floor:
            counters["floor"] += 1
            floor = Floor(block_id=block.id, floor_label=label or f"F-{suffix}-{counters['floor']}", is_active=True)
            db_session.add(floor)
            db_session.flush()
            return floor

        def create_room(
            self,
            block: Block,
            floor: Floor | None,
            room_code: str | None = None,
            room_type: str = "4_IN_ROOM",
            beds_count: int = 4,
            unit_price_per_bed: Decimal = Decimal("1000.00"),
            is_active: bool = True,
        ) -> Room:
            counters["room"] += 1
            room = Room(
                block_id=block.id,
                floor_id=floor.id if floor else None,
                room_code=room_code or f"R-{suffix}-{counters['room']}",
                room_type=room_type,
                beds_count=beds_count,
                unit_price_per_bed=unit_price_per_bed,
                is_active=is_active,
            )
            db_session.add(room)
            db_session.flush()
            return room

        def create_bed(self, room: Room, bed_number: int, status: str = "AVAILABLE") -> Bed:
            bed = Bed(
                room_id=room.id,
                bed_number=bed_number,
                bed_label=f"B{bed_number}",
                status=status,
            )
            db_session.add(bed)
            db_session.flush()
            return bed

        def create_tenant(self, name: str | None = None, status: str = "prospect") -> Tenant:
            counters["tenant"] += 1
            tenant = Tenant(name=name or f"Tenant-{suffix}-{counters['tenant']}", status=status)
            db_session.add(tenant)
            db_session.flush()
            return tenant

        def create_user(
            self,
            email: str | None = None,
            full_name: str = "Test User",
            is_admin: bool = True,
            tenant: Tenant | None = None,
        ) -> User:
            counters["user"] += 1
            user = User(
                tenant_id=tenant.id if tenant else None,
                email=email or f"user-{suffix}-{counters['user']}@example.com",
                full_name=full_name,
                password_hash="x",
                is_admin=is_admin,
                is_active=True,
            )
            db_session.add(user)
            db_session.flush()
            return user

        def create_invoice(
            self,
            tenant: Tenant,
            user: User | None = None,
            reserved_bed: Bed | None = None,
            status: str = "approved",
            total: Decimal = Decimal("1000.00"),
            currency: str = "GHS",
            created_at: datetime | None = None,
        ) -> Invoice:
            counters["invoice"] += 1
            now = created_at or self.now()
            invoice = Invoice(
                tenant_id=tenant.id,
                user_id=user.id if user else None,
                reserved_bed_id=reserved_bed.id if reserved_bed else None,
                invoice_no=f"TINV-{suffix}-{counters['invoice']:04d}",
                billing_year=now.year,
                status=status,
                currency=currency,
                subtotal=total,
                tax=Decimal("0"),
                discount=Decimal("0"),
                total=total,
                issued_at=now,
                due_at=now + timedelta(days=7),
                created_at=now,
                updated_at=now,
            )
            db_session.add(invoice)
            db_session.flush()
            return invoice

        def create_payment(
            self,
            tenant: Tenant,
            invoice: Invoice,
            amount: Decimal,
            user: User | None = None,
            status: str = "completed",
            paid_at: datetime | None = None,
        ) -> Payment:
            counters["payment"] += 1
            payment = Payment(
                tenant_id=tenant.id,
                invoice_id=invoice.id,
                handled_by_user_id=user.id if user else None,
                payment_no=f"TPAY-{suffix}-{counters['payment']:04d}",
                amount=amount,
                currency=invoice.currency,
                method="cash",
                reference=f"REF-{suffix}-{counters['payment']:04d}",
                status=status,
                paid_at=paid_at or self.now(),
            )
            db_session.add(payment)
            db_session.flush()
            return payment

        def create_reservation(
            self,
            bed: Bed,
            tenant: Tenant,
            invoice: Invoice | None = None,
            status: str = "ACTIVE",
            expires_at: datetime | None = None,
            user: User | None = None,
        ) -> BedReservation:
            now = self.now()
            reservation = BedReservation(
                bed_id=bed.id,
                tenant_id=tenant.id,
                invoice_id=invoice.id if invoice else None,
                status=status,
                reserved_at=now,
                expires_at=expires_at or (now + timedelta(hours=24)),
                reserved_by=user.id if user else None,
            )
            db_session.add(reservation)
            db_session.flush()
            return reservation

        def create_allocation(
            self,
            bed: Bed,
            tenant: Tenant,
            invoice: Invoice | None = None,
            status: str = "CONFIRMED",
            user: User | None = None,
        ) -> Allocation:
            allocation = Allocation(
                bed_id=bed.id,
                tenant_id=tenant.id,
                invoice_id=invoice.id if invoice else None,
                status=status,
                start_date=self.now(),
                ended_by=user.id if user else None,
            )
            db_session.add(allocation)
            db_session.flush()
            return allocation

    return Factory()
