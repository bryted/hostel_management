"""Add discount amount to invoices.

Revision ID: 0013_invoice_discount
Revises: 0012_invoice_reserved_bed
Create Date: 2026-02-01 12:20:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_invoice_discount"
down_revision = "0012_invoice_reserved_bed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("discount", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("invoices", "discount")
