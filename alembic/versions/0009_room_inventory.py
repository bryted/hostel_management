"""Add room inventory and bed allocation tables.

Revision ID: 0009_room_inventory
Revises: 0008_admin_contacts_global
Create Date: 2026-01-31 18:40:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_room_inventory"
down_revision = "0008_admin_contacts_global"
branch_labels = None
depends_on = None

bed_status_enum = postgresql.ENUM(
    "AVAILABLE",
    "RESERVED",
    "OCCUPIED",
    "OUT_OF_SERVICE",
    name="bed_status",
)
bed_status_enum_notype = postgresql.ENUM(
    "AVAILABLE",
    "RESERVED",
    "OCCUPIED",
    "OUT_OF_SERVICE",
    name="bed_status",
    create_type=False,
)
bed_reservation_status_enum = postgresql.ENUM(
    "ACTIVE",
    "EXPIRED",
    "CANCELLED",
    name="bed_reservation_status",
)
bed_reservation_status_enum_notype = postgresql.ENUM(
    "ACTIVE",
    "EXPIRED",
    "CANCELLED",
    name="bed_reservation_status",
    create_type=False,
)
allocation_status_enum = postgresql.ENUM(
    "CONFIRMED",
    "ENDED",
    name="allocation_status",
)
allocation_status_enum_notype = postgresql.ENUM(
    "CONFIRMED",
    "ENDED",
    name="allocation_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    bed_status_enum.create(bind, checkfirst=True)
    bed_reservation_status_enum.create(bind, checkfirst=True)
    allocation_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "blocks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "floors",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("block_id", sa.BigInteger(), sa.ForeignKey("blocks.id"), nullable=False),
        sa.Column("floor_label", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "rooms",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("block_id", sa.BigInteger(), sa.ForeignKey("blocks.id"), nullable=False),
        sa.Column("floor_id", sa.BigInteger(), sa.ForeignKey("floors.id")),
        sa.Column("room_code", sa.String(length=50), nullable=False),
        sa.Column("room_type", sa.String(length=50)),
        sa.Column("beds_count", sa.Integer(), nullable=False),
        sa.Column("unit_price_per_bed", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "beds",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("room_id", sa.BigInteger(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("bed_number", sa.Integer(), nullable=False),
        sa.Column("bed_label", sa.String(length=50), nullable=False),
        sa.Column("status", bed_status_enum_notype, server_default="AVAILABLE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("room_id", "bed_number", name="uq_beds_room_id_bed_number"),
    )

    op.create_table(
        "bed_reservations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("bed_id", sa.BigInteger(), sa.ForeignKey("beds.id"), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), sa.ForeignKey("invoices.id")),
        sa.Column(
            "status",
            bed_reservation_status_enum_notype,
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("reserved_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("reserved_by", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_by", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("cancel_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "allocations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("bed_id", sa.BigInteger(), sa.ForeignKey("beds.id"), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), sa.ForeignKey("invoices.id")),
        sa.Column(
            "status",
            allocation_status_enum_notype,
            server_default="CONFIRMED",
            nullable=False,
        ),
        sa.Column("start_date", sa.DateTime(timezone=True)),
        sa.Column("end_date", sa.DateTime(timezone=True)),
        sa.Column("ended_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("ended_by", sa.BigInteger(), sa.ForeignKey("users.id")),
    )

    op.create_table(
        "bed_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("bed_id", sa.BigInteger(), sa.ForeignKey("beds.id"), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("invoice_id", sa.BigInteger(), sa.ForeignKey("invoices.id")),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id")),
        sa.Column("detail_json", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "allocation_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("allocation_id", sa.BigInteger(), sa.ForeignKey("allocations.id"), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("detail_json", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column(
        "invoices",
        sa.Column(
            "billing_year",
            sa.Integer(),
            server_default=sa.text("date_part('year', now())::int"),
            nullable=False,
        ),
    )

    op.create_index("ix_beds_status", "beds", ["status"])
    op.create_index("ix_rooms_block_id_floor_id", "rooms", ["block_id", "floor_id"])
    op.create_index(
        "ix_bed_reservations_expires_at_status", "bed_reservations", ["expires_at", "status"]
    )
    op.create_index(
        "ix_invoices_billing_year_status", "invoices", ["billing_year", "status"]
    )
    op.create_index("ix_payments_created_at", "payments", ["created_at"])

    op.create_index(
        "uq_bed_reservations_active_bed_id",
        "bed_reservations",
        ["bed_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_allocations_confirmed_bed_id",
        "allocations",
        ["bed_id"],
        unique=True,
        postgresql_where=sa.text("status = 'CONFIRMED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_allocations_confirmed_bed_id", table_name="allocations")
    op.drop_index("uq_bed_reservations_active_bed_id", table_name="bed_reservations")

    op.drop_index("ix_payments_created_at", table_name="payments")
    op.drop_index("ix_invoices_billing_year_status", table_name="invoices")
    op.drop_index("ix_bed_reservations_expires_at_status", table_name="bed_reservations")
    op.drop_index("ix_rooms_block_id_floor_id", table_name="rooms")
    op.drop_index("ix_beds_status", table_name="beds")

    op.drop_column("invoices", "billing_year")

    op.drop_table("allocation_events")
    op.drop_table("bed_events")
    op.drop_table("allocations")
    op.drop_table("bed_reservations")
    op.drop_table("beds")
    op.drop_table("rooms")
    op.drop_table("floors")
    op.drop_table("blocks")

    bind = op.get_bind()
    allocation_status_enum.drop(bind, checkfirst=True)
    bed_reservation_status_enum.drop(bind, checkfirst=True)
    bed_status_enum.drop(bind, checkfirst=True)
