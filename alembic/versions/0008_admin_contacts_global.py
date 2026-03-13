"""Allow admin contacts without tenant association.

Revision ID: 0008_admin_contacts_global
Revises: 0007_sms_sender_id
Create Date: 2026-01-31 16:05:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0008_admin_contacts_global"
down_revision = "0007_sms_sender_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "admin_contacts",
        "tenant_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "admin_contacts",
        "tenant_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
