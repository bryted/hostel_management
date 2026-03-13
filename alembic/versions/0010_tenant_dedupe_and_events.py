"""Tenant dedupe helpers and audit events.

Revision ID: 0010_tenant_dedupe_and_events
Revises: 0009_room_inventory
Create Date: 2026-02-01 09:10:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_tenant_dedupe_and_events"
down_revision = "0009_room_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("normalized_phone", sa.String(length=20)))

    op.create_table(
        "tenant_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("detail_json", postgresql.JSONB()),
    )

    op.execute(
        """
        WITH cleaned AS (
            SELECT
                id,
                regexp_replace(COALESCE(phone, ''), '\\D', '', 'g') AS digits
            FROM tenants
        )
        UPDATE tenants t
        SET normalized_phone = CASE
            WHEN c.digits = '' THEN NULL
            WHEN c.digits LIKE '00%' THEN substr(c.digits, 3)
            ELSE c.digits
        END
        FROM cleaned c
        WHERE t.id = c.id;
        """
    )

    op.execute(
        """
        UPDATE tenants
        SET normalized_phone = CASE
            WHEN normalized_phone LIKE '0%' AND length(normalized_phone) = 10
                THEN '233' || substr(normalized_phone, 2)
            ELSE normalized_phone
        END
        WHERE normalized_phone IS NOT NULL;
        """
    )

    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   normalized_phone,
                   row_number() OVER (PARTITION BY normalized_phone ORDER BY id) AS rn
            FROM tenants
            WHERE normalized_phone IS NOT NULL
              AND status = 'active'
        )
        UPDATE tenants t
        SET normalized_phone = NULL
        FROM ranked r
        WHERE t.id = r.id
          AND r.rn > 1;
        """
    )

    op.create_index("ix_tenants_phone", "tenants", ["phone"])
    op.create_index("ix_payments_reference", "payments", ["reference"])
    op.create_index("ix_allocations_status", "allocations", ["status"])
    op.create_index(
        "uq_tenants_normalized_phone_active",
        "tenants",
        ["normalized_phone"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND normalized_phone IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_tenants_normalized_phone_active", table_name="tenants")
    op.drop_index("ix_allocations_status", table_name="allocations")
    op.drop_index("ix_payments_reference", table_name="payments")
    op.drop_index("ix_tenants_phone", table_name="tenants")

    op.drop_table("tenant_events")
    op.drop_column("tenants", "normalized_phone")
