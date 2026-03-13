"""Initial schema.

Revision ID: 0001_initial
Revises: 
Create Date: 2026-01-29 09:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


INVOICE_NO_DEFAULT = (
    "('INV-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('invoice_no_seq')::text, 6, '0'))"
)
PAYMENT_NO_DEFAULT = (
    "('PAY-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('payment_no_seq')::text, 6, '0'))"
)
RECEIPT_NO_DEFAULT = (
    "('REC-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('receipt_no_seq')::text, 6, '0'))"
)


def upgrade() -> None:
    op.execute("CREATE SEQUENCE invoice_no_seq START WITH 1 INCREMENT BY 1")
    op.execute("CREATE SEQUENCE payment_no_seq START WITH 1 INCREMENT BY 1")
    op.execute("CREATE SEQUENCE receipt_no_seq START WITH 1 INCREMENT BY 1")

    op.create_table(
        "tenants",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "is_admin",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "email"),
    )

    op.create_table(
        "admin_contacts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "invoices",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "invoice_no",
            sa.String(length=32),
            server_default=sa.text(INVOICE_NO_DEFAULT),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default="USD",
            nullable=False,
        ),
        sa.Column(
            "subtotal",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "tax",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "total",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_no"),
    )

    op.create_table(
        "invoice_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "line_no",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column(
            "quantity",
            sa.Numeric(precision=12, scale=2),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "unit_price",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "invoice_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "event_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "payment_no",
            sa.String(length=32),
            server_default=sa.text(PAYMENT_NO_DEFAULT),
            nullable=False,
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default="USD",
            nullable=False,
        ),
        sa.Column("method", sa.String(length=50), nullable=True),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_no"),
    )

    op.create_table(
        "receipts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("payment_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "receipt_no",
            sa.String(length=32),
            server_default=sa.text(RECEIPT_NO_DEFAULT),
            nullable=False,
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default="USD",
            nullable=False,
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_no"),
    )

    op.create_table(
        "receipt_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("receipt_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "event_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "notification_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("outbox_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "event_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["outbox_id"], ["notification_outbox.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("notification_events")
    op.drop_table("notification_outbox")
    op.drop_table("receipt_events")
    op.drop_table("receipts")
    op.drop_table("payments")
    op.drop_table("invoice_events")
    op.drop_table("invoice_items")
    op.drop_table("invoices")
    op.drop_table("admin_contacts")
    op.drop_table("users")
    op.drop_table("tenants")

    op.execute("DROP SEQUENCE IF EXISTS receipt_no_seq")
    op.execute("DROP SEQUENCE IF EXISTS payment_no_seq")
    op.execute("DROP SEQUENCE IF EXISTS invoice_no_seq")
