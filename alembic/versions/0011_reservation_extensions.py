"""Add reservation extension fields.

Revision ID: 0011_reservation_extensions
Revises: 0010_tenant_dedupe_and_events
Create Date: 2026-02-01 09:20:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_reservation_extensions"
down_revision = "0010_tenant_dedupe_and_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bed_reservations", sa.Column("extended_at", sa.DateTime(timezone=True)))
    op.add_column("bed_reservations", sa.Column("extended_by", sa.BigInteger()))
    op.add_column("bed_reservations", sa.Column("extension_reason", sa.Text()))
    op.add_column(
        "bed_reservations",
        sa.Column("extension_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_foreign_key(
        "fk_bed_reservations_extended_by_users",
        "bed_reservations",
        "users",
        ["extended_by"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_bed_reservations_extended_by_users",
        "bed_reservations",
        type_="foreignkey",
    )
    op.drop_column("bed_reservations", "extension_count")
    op.drop_column("bed_reservations", "extension_reason")
    op.drop_column("bed_reservations", "extended_by")
    op.drop_column("bed_reservations", "extended_at")
