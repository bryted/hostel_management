"""Add sms_sender_id to notification settings.

Revision ID: 0007_sms_sender_id
Revises: 0006_payment_handled_by_user
Create Date: 2026-01-31 15:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0007_sms_sender_id"
down_revision = "0006_payment_handled_by_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_settings",
        sa.Column("sms_sender_id", sa.String(length=11), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_settings", "sms_sender_id")
