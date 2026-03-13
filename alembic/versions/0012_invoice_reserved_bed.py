"""Add reserved bed reference to invoices.

Revision ID: 0012_invoice_reserved_bed
Revises: 0011_reservation_extensions
Create Date: 2026-02-01 11:15:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_invoice_reserved_bed"
down_revision = "0011_reservation_extensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("reserved_bed_id", sa.BigInteger()))
    op.create_foreign_key(
        "fk_invoices_reserved_bed_id_beds",
        "invoices",
        "beds",
        ["reserved_bed_id"],
        ["id"],
    )
    op.create_index("ix_invoices_reserved_bed_id", "invoices", ["reserved_bed_id"])


def downgrade() -> None:
    op.drop_index("ix_invoices_reserved_bed_id", table_name="invoices")
    op.drop_constraint("fk_invoices_reserved_bed_id_beds", "invoices", type_="foreignkey")
    op.drop_column("invoices", "reserved_bed_id")
