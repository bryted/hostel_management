"""Security hardening for notification secrets and currency default alignment.

Revision ID: 0016_security_currency_alignment
Revises: 0015_inventory_flow
Create Date: 2026-02-14 00:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_security_currency_alignment"
down_revision = "0015_inventory_flow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "invoices",
        "currency",
        existing_type=sa.String(length=3),
        existing_nullable=False,
        server_default="GHS",
    )
    op.alter_column(
        "payments",
        "currency",
        existing_type=sa.String(length=3),
        existing_nullable=False,
        server_default="GHS",
    )
    op.alter_column(
        "receipts",
        "currency",
        existing_type=sa.String(length=3),
        existing_nullable=False,
        server_default="GHS",
    )

    # Notification transport credentials are now environment-managed.
    op.execute(
        """
        UPDATE notification_settings
        SET whatsapp_access_token = NULL,
            whatsapp_phone_number_id = NULL,
            whatsapp_api_version = NULL,
            sms_api_url = NULL,
            sms_api_key = NULL,
            sms_sender_id = NULL,
            smtp_host = NULL,
            smtp_port = NULL,
            smtp_user = NULL,
            smtp_password = NULL,
            smtp_from = NULL
        """
    )


def downgrade() -> None:
    op.alter_column(
        "receipts",
        "currency",
        existing_type=sa.String(length=3),
        existing_nullable=False,
        server_default="USD",
    )
    op.alter_column(
        "payments",
        "currency",
        existing_type=sa.String(length=3),
        existing_nullable=False,
        server_default="USD",
    )
    op.alter_column(
        "invoices",
        "currency",
        existing_type=sa.String(length=3),
        existing_nullable=False,
        server_default="USD",
    )
