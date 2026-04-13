"""Add partial unique indexes for active allocations.

Revision ID: 0019_active_allocation_uniques
Revises: 0018_active_reservation_uniques
Create Date: 2026-04-11 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_active_allocation_uniques"
down_revision = "0018_active_reservation_uniques"
branch_labels = None
depends_on = None


def _existing_indexes() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes("allocations")}


def upgrade() -> None:
    existing_indexes = _existing_indexes()
    if "uq_allocations_confirmed_bed_id" not in existing_indexes:
        op.create_index(
            "uq_allocations_confirmed_bed_id",
            "allocations",
            ["bed_id"],
            unique=True,
            postgresql_where=sa.text("status = 'CONFIRMED'"),
        )
    if "uq_allocations_confirmed_invoice_id" not in existing_indexes:
        op.create_index(
            "uq_allocations_confirmed_invoice_id",
            "allocations",
            ["invoice_id"],
            unique=True,
            postgresql_where=sa.text("invoice_id IS NOT NULL AND status = 'CONFIRMED'"),
        )
    if "uq_allocations_confirmed_tenant_id" not in existing_indexes:
        op.create_index(
            "uq_allocations_confirmed_tenant_id",
            "allocations",
            ["tenant_id"],
            unique=True,
            postgresql_where=sa.text("status = 'CONFIRMED'"),
        )


def downgrade() -> None:
    existing_indexes = _existing_indexes()
    if "uq_allocations_confirmed_tenant_id" in existing_indexes:
        op.drop_index("uq_allocations_confirmed_tenant_id", table_name="allocations")
    if "uq_allocations_confirmed_invoice_id" in existing_indexes:
        op.drop_index("uq_allocations_confirmed_invoice_id", table_name="allocations")
    if "uq_allocations_confirmed_bed_id" in existing_indexes:
        op.drop_index("uq_allocations_confirmed_bed_id", table_name="allocations")
