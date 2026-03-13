"""Add payment reference and receipt printed count.

Revision ID: 0003_payment_receipt_fields
Revises: 0002_tenant_contact_fields
Create Date: 2026-01-29 10:35:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0003_payment_receipt_fields"
down_revision = "0002_tenant_contact_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("reference", sa.String(length=100), nullable=True))
    op.add_column(
        "receipts",
        sa.Column("printed_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("receipts", "printed_count")
    op.drop_column("payments", "reference")
