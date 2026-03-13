from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )


INVOICE_NO_DEFAULT = (
    "('INV-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('invoice_no_seq')::text, 6, '0'))"
)
PAYMENT_NO_DEFAULT = (
    "('PAY-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('payment_no_seq')::text, 6, '0'))"
)
RECEIPT_NO_DEFAULT = (
    "('REC-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('receipt_no_seq')::text, 6, '0'))"
)

BED_STATUS_ENUM = sa.Enum(
    "AVAILABLE",
    "RESERVED",
    "OCCUPIED",
    "OUT_OF_SERVICE",
    name="bed_status",
)
BED_RESERVATION_STATUS_ENUM = sa.Enum(
    "ACTIVE",
    "EXPIRED",
    "CANCELLED",
    name="bed_reservation_status",
)
ALLOCATION_STATUS_ENUM = sa.Enum(
    "CONFIRMED",
    "ENDED",
    name="allocation_status",
)


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(sa.String(255))
    phone: Mapped[str | None] = mapped_column(sa.String(50))
    normalized_phone: Mapped[str | None] = mapped_column(sa.String(20))
    room: Mapped[str | None] = mapped_column(sa.String(50))
    status: Mapped[str] = mapped_column(sa.String(50), nullable=False, server_default="active")

    users: Mapped[list[User]] = relationship("User", back_populates="tenant")
    admin_contacts: Mapped[list[AdminContact]] = relationship(
        "AdminContact", back_populates="tenant"
    )
    reservations: Mapped[list[BedReservation]] = relationship(
        "BedReservation", back_populates="tenant"
    )
    allocations: Mapped[list[Allocation]] = relationship(
        "Allocation", back_populates="tenant"
    )
    events: Mapped[list[TenantEvent]] = relationship("TenantEvent", back_populates="tenant")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("tenants.id"), nullable=True
    )
    email: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))

    tenant: Mapped[Tenant | None] = relationship("Tenant", back_populates="users")

    __table_args__ = (sa.UniqueConstraint("tenant_id", "email"),)


class AdminContact(Base, TimestampMixin):
    __tablename__ = "admin_contacts"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("tenants.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    email: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(sa.String(50))
    notes: Mapped[str | None] = mapped_column(sa.Text)

    tenant: Mapped[Tenant | None] = relationship("Tenant", back_populates="admin_contacts")


class TenantEvent(Base):
    __tablename__ = "tenant_events"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("tenants.id"))
    event_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    event_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    detail_json: Mapped[dict | None] = mapped_column(JSONB)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="events")
    user: Mapped[User | None] = relationship("User")


class Block(Base, TimestampMixin):
    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))

    floors: Mapped[list[Floor]] = relationship("Floor", back_populates="block")
    rooms: Mapped[list[Room]] = relationship("Room", back_populates="block")


class Floor(Base, TimestampMixin):
    __tablename__ = "floors"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    block_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("blocks.id"))
    floor_label: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))

    block: Mapped[Block] = relationship("Block", back_populates="floors")
    rooms: Mapped[list[Room]] = relationship("Room", back_populates="floor")


class Room(Base, TimestampMixin):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    block_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("blocks.id"))
    floor_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("floors.id"))
    room_code: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    room_type: Mapped[str | None] = mapped_column(sa.String(50))
    beds_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    unit_price_per_bed: Mapped[float] = mapped_column(
        sa.Numeric(12, 2), nullable=False, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))

    block: Mapped[Block] = relationship("Block", back_populates="rooms")
    floor: Mapped[Floor | None] = relationship("Floor", back_populates="rooms")
    beds: Mapped[list[Bed]] = relationship("Bed", back_populates="room")


class Bed(Base, TimestampMixin):
    __tablename__ = "beds"
    __table_args__ = (sa.UniqueConstraint("room_id", "bed_number", name="uq_beds_room_id_bed_number"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    room_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("rooms.id"))
    bed_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    bed_label: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        BED_STATUS_ENUM,
        nullable=False,
        server_default="AVAILABLE",
    )

    room: Mapped[Room] = relationship("Room", back_populates="beds")
    reservations: Mapped[list[BedReservation]] = relationship(
        "BedReservation", back_populates="bed"
    )
    allocations: Mapped[list[Allocation]] = relationship("Allocation", back_populates="bed")


class BedReservation(Base, TimestampMixin):
    __tablename__ = "bed_reservations"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    bed_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("beds.id"))
    tenant_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("tenants.id"))
    invoice_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("invoices.id"))
    status: Mapped[str] = mapped_column(
        BED_RESERVATION_STATUS_ENUM,
        nullable=False,
        server_default="ACTIVE",
    )
    reserved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    reserved_by: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    extended_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    extended_by: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    extension_reason: Mapped[str | None] = mapped_column(sa.Text)
    extension_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    cancelled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    cancelled_by: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(sa.Text)

    bed: Mapped[Bed] = relationship("Bed", back_populates="reservations")
    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="reservations")
    invoice: Mapped[Invoice | None] = relationship("Invoice", back_populates="reservations")
    reserved_by_user: Mapped[User | None] = relationship("User", foreign_keys=[reserved_by])
    extended_by_user: Mapped[User | None] = relationship("User", foreign_keys=[extended_by])
    cancelled_by_user: Mapped[User | None] = relationship("User", foreign_keys=[cancelled_by])


class Allocation(Base, TimestampMixin):
    __tablename__ = "allocations"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    bed_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("beds.id"))
    tenant_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("tenants.id"))
    invoice_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("invoices.id"))
    status: Mapped[str] = mapped_column(
        ALLOCATION_STATUS_ENUM,
        nullable=False,
        server_default="CONFIRMED",
    )
    start_date: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    end_date: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    ended_reason: Mapped[str | None] = mapped_column(sa.Text)
    ended_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    ended_by: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))

    bed: Mapped[Bed] = relationship("Bed", back_populates="allocations")
    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="allocations")
    invoice: Mapped[Invoice | None] = relationship("Invoice", back_populates="allocations")
    ended_by_user: Mapped[User | None] = relationship("User", foreign_keys=[ended_by])


class BedEvent(Base):
    __tablename__ = "bed_events"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    bed_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("beds.id"))
    event_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    user_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    invoice_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("invoices.id"))
    tenant_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("tenants.id"))
    detail_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    bed: Mapped[Bed] = relationship("Bed")
    user: Mapped[User | None] = relationship("User")
    invoice: Mapped[Invoice | None] = relationship("Invoice")
    tenant: Mapped[Tenant | None] = relationship("Tenant")


class AllocationEvent(Base):
    __tablename__ = "allocation_events"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    allocation_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("allocations.id"))
    event_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    user_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    detail_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    allocation: Mapped[Allocation] = relationship("Allocation")
    user: Mapped[User | None] = relationship("User")


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("tenants.id"))
    user_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reserved_bed_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("beds.id"), nullable=True
    )
    invoice_no: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        unique=True,
        server_default=sa.text(INVOICE_NO_DEFAULT),
    )
    billing_year: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("date_part('year', now())::int"),
    )
    status: Mapped[str] = mapped_column(sa.String(50), nullable=False, server_default="draft")
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, server_default="GHS")
    subtotal: Mapped[float] = mapped_column(sa.Numeric(12, 2), nullable=False, server_default="0")
    tax: Mapped[float] = mapped_column(sa.Numeric(12, 2), nullable=False, server_default="0")
    discount: Mapped[float] = mapped_column(sa.Numeric(12, 2), nullable=False, server_default="0")
    total: Mapped[float] = mapped_column(sa.Numeric(12, 2), nullable=False, server_default="0")
    issued_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(sa.Text)

    tenant: Mapped[Tenant] = relationship("Tenant")
    user: Mapped[User | None] = relationship("User")
    reserved_bed: Mapped[Bed | None] = relationship("Bed", foreign_keys=[reserved_bed_id])
    items: Mapped[list[InvoiceItem]] = relationship("InvoiceItem", back_populates="invoice")
    events: Mapped[list[InvoiceEvent]] = relationship("InvoiceEvent", back_populates="invoice")
    reservations: Mapped[list[BedReservation]] = relationship(
        "BedReservation", back_populates="invoice"
    )
    allocations: Mapped[list[Allocation]] = relationship(
        "Allocation", back_populates="invoice"
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    invoice_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("invoices.id"))
    line_no: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    description: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    quantity: Mapped[float] = mapped_column(sa.Numeric(12, 2), nullable=False, server_default="1")
    unit_price: Mapped[float] = mapped_column(sa.Numeric(12, 2), nullable=False, server_default="0")
    amount: Mapped[float] = mapped_column(sa.Numeric(12, 2), nullable=False, server_default="0")

    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="items")


class InvoiceEvent(Base):
    __tablename__ = "invoice_events"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    invoice_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("invoices.id"))
    event_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    event_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    payload: Mapped[dict | None] = mapped_column(JSONB)

    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="events")


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("tenants.id"))
    invoice_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("invoices.id"))
    handled_by_user_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id"), nullable=True
    )
    payment_no: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        unique=True,
        server_default=sa.text(PAYMENT_NO_DEFAULT),
    )
    amount: Mapped[float] = mapped_column(sa.Numeric(12, 2), nullable=False, server_default="0")
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, server_default="GHS")
    method: Mapped[str | None] = mapped_column(sa.String(50))
    reference: Mapped[str | None] = mapped_column(sa.String(100))
    status: Mapped[str] = mapped_column(sa.String(50), nullable=False, server_default="pending")
    paid_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    voided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(sa.Text)

    tenant: Mapped[Tenant] = relationship("Tenant")
    invoice: Mapped[Invoice | None] = relationship("Invoice")
    handled_by_user: Mapped[User | None] = relationship("User")


class Receipt(Base, TimestampMixin):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("tenants.id"))
    payment_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("payments.id"))
    receipt_no: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        unique=True,
        server_default=sa.text(RECEIPT_NO_DEFAULT),
    )
    amount: Mapped[float] = mapped_column(sa.Numeric(12, 2), nullable=False, server_default="0")
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, server_default="GHS")
    issued_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    printed_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")

    tenant: Mapped[Tenant] = relationship("Tenant")
    payment: Mapped[Payment | None] = relationship("Payment")
    events: Mapped[list[ReceiptEvent]] = relationship("ReceiptEvent", back_populates="receipt")


class ReceiptEvent(Base):
    __tablename__ = "receipt_events"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    receipt_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("receipts.id"))
    event_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    event_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    payload: Mapped[dict | None] = mapped_column(JSONB)

    receipt: Mapped[Receipt] = relationship("Receipt", back_populates="events")


class NotificationOutbox(Base, TimestampMixin):
    __tablename__ = "notification_outbox"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("tenants.id"))
    channel: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    recipient: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(sa.String(255))
    body: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(50), nullable=False, server_default="queued")
    attempt_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    scheduled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(sa.Text)

    tenant: Mapped[Tenant] = relationship("Tenant")
    events: Mapped[list[NotificationEvent]] = relationship(
        "NotificationEvent", back_populates="outbox"
    )


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    outbox_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("notification_outbox.id")
    )
    event_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    event_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    payload: Mapped[dict | None] = mapped_column(JSONB)

    outbox: Mapped[NotificationOutbox] = relationship(
        "NotificationOutbox", back_populates="events"
    )


class HostelProfile(Base, TimestampMixin):
    __tablename__ = "hostel_profile"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    name: Mapped[str | None] = mapped_column(sa.String(255))
    address: Mapped[str | None] = mapped_column(sa.Text)
    phone: Mapped[str | None] = mapped_column(sa.String(50))
    email: Mapped[str | None] = mapped_column(sa.String(255))
    logo: Mapped[bytes | None] = mapped_column(sa.LargeBinary)
    logo_mime: Mapped[str | None] = mapped_column(sa.String(100))
    footer_text: Mapped[str | None] = mapped_column(sa.Text)


class NotificationSettings(Base, TimestampMixin):
    __tablename__ = "notification_settings"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    whatsapp_access_token: Mapped[str | None] = mapped_column(sa.Text)
    whatsapp_phone_number_id: Mapped[str | None] = mapped_column(sa.String(100))
    whatsapp_api_version: Mapped[str | None] = mapped_column(sa.String(20))
    sms_api_url: Mapped[str | None] = mapped_column(sa.Text)
    sms_api_key: Mapped[str | None] = mapped_column(sa.Text)
    sms_sender_id: Mapped[str | None] = mapped_column(sa.String(11))
    smtp_host: Mapped[str | None] = mapped_column(sa.String(255))
    smtp_port: Mapped[int | None] = mapped_column(sa.Integer)
    smtp_user: Mapped[str | None] = mapped_column(sa.String(255))
    smtp_password: Mapped[str | None] = mapped_column(sa.Text)
    smtp_from: Mapped[str | None] = mapped_column(sa.String(255))
    mock_mode: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    block_duplicate_payment_reference: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    notification_max_attempts: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="3"
    )
    notification_retry_delay_seconds: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="300"
    )
    reservation_default_hold_hours: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="24"
    )
    auto_approve_invoices: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
