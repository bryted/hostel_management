"""Add partial unique indexes for active bed reservations.

Revision ID: 0018_active_reservation_uniques
Revises: 0017_provider_controls
Create Date: 2026-04-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_active_reservation_uniques"
down_revision = "0017_provider_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("bed_reservations")}

    if "uq_bed_reservations_active_bed_id" not in existing_indexes:
        op.create_index(
            "uq_bed_reservations_active_bed_id",
            "bed_reservations",
            ["bed_id"],
            unique=True,
            postgresql_where=sa.text("status = 'ACTIVE'"),
        )
    if "uq_bed_reservations_active_invoice_id" not in existing_indexes:
        op.create_index(
            "uq_bed_reservations_active_invoice_id",
            "bed_reservations",
            ["invoice_id"],
            unique=True,
            postgresql_where=sa.text("invoice_id IS NOT NULL AND status = 'ACTIVE'"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("bed_reservations")}

    if "uq_bed_reservations_active_invoice_id" in existing_indexes:
        op.drop_index("uq_bed_reservations_active_invoice_id", table_name="bed_reservations")
    if "uq_bed_reservations_active_bed_id" in existing_indexes:
        op.drop_index("uq_bed_reservations_active_bed_id", table_name="bed_reservations")
