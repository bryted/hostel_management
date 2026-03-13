"""Add payment void fields.

Revision ID: 0004_payment_void_fields
Revises: 0003_payment_receipt_fields
Create Date: 2026-01-29 11:05:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0004_payment_void_fields"
down_revision = "0003_payment_receipt_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payments", sa.Column("void_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "void_reason")
    op.drop_column("payments", "voided_at")
