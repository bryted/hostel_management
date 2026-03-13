"""Operational hardening indexes and settings.

Revision ID: 0014_operational_hardening
Revises: 0013_invoice_discount
Create Date: 2026-02-13 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_operational_hardening"
down_revision = "0013_invoice_discount"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_settings",
        sa.Column(
            "block_duplicate_payment_reference",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "notification_settings",
        sa.Column(
            "notification_max_attempts",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )
    op.add_column(
        "notification_settings",
        sa.Column(
            "notification_retry_delay_seconds",
            sa.Integer(),
            nullable=False,
            server_default="300",
        ),
    )
    op.add_column(
        "notification_outbox",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_index(
        "ix_notification_outbox_status_scheduled_created",
        "notification_outbox",
        ["status", "scheduled_at", "created_at"],
    )
    op.create_index(
        "ix_payments_invoice_status_paid_at",
        "payments",
        ["invoice_id", "status", "paid_at"],
    )
    op.create_index(
        "ix_allocations_invoice_status",
        "allocations",
        ["invoice_id", "status"],
    )
    op.create_index(
        "ix_tenant_events_tenant_event_at",
        "tenant_events",
        ["tenant_id", "event_type", "event_at"],
    )

    bind = op.get_bind()
    duplicate_confirmed_invoice_count = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT invoice_id
                FROM allocations
                WHERE status = 'CONFIRMED' AND invoice_id IS NOT NULL
                GROUP BY invoice_id
                HAVING count(*) > 1
            ) d
            """
        )
    ).scalar_one()
    if int(duplicate_confirmed_invoice_count or 0) > 0:
        raise RuntimeError(
            "Cannot enforce unique confirmed allocation per invoice because duplicates exist."
        )
    op.create_index(
        "uq_allocations_confirmed_invoice_id",
        "allocations",
        ["invoice_id"],
        unique=True,
        postgresql_where=sa.text("status = 'CONFIRMED' AND invoice_id IS NOT NULL"),
    )

    duplicate_count = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT lower(email)
                FROM users
                GROUP BY lower(email)
                HAVING count(*) > 1
            ) d
            """
        )
    ).scalar_one()
    if int(duplicate_count or 0) > 0:
        raise RuntimeError(
            "Cannot create unique lower(email) index on users because duplicates exist."
        )

    op.execute("CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_email_lower")

    op.drop_index("uq_allocations_confirmed_invoice_id", table_name="allocations")
    op.drop_index("ix_tenant_events_tenant_event_at", table_name="tenant_events")
    op.drop_index("ix_allocations_invoice_status", table_name="allocations")
    op.drop_index("ix_payments_invoice_status_paid_at", table_name="payments")
    op.drop_index(
        "ix_notification_outbox_status_scheduled_created",
        table_name="notification_outbox",
    )

    op.drop_column("notification_outbox", "attempt_count")
    op.drop_column("notification_settings", "notification_retry_delay_seconds")
    op.drop_column("notification_settings", "notification_max_attempts")
    op.drop_column("notification_settings", "block_duplicate_payment_reference")
