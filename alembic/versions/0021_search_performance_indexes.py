"""add search performance indexes

Revision ID: 0021_search_performance_indexes
Revises: 0020_financial_query_indexes
Create Date: 2026-04-13 00:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0021_search_performance_indexes"
down_revision = "0020_financial_query_indexes"
branch_labels = None
depends_on = None


SEARCH_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_tenants_name_trgm ON tenants USING gin (lower(name) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_tenants_email_trgm ON tenants USING gin (lower(email) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_tenants_phone_trgm ON tenants USING gin (lower(phone) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_tenants_normalized_phone ON tenants (normalized_phone)",
    "CREATE INDEX IF NOT EXISTS ix_tenants_status ON tenants (status)",
    "CREATE INDEX IF NOT EXISTS ix_users_full_name_trgm ON users USING gin (lower(full_name) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_users_email_trgm ON users USING gin (lower(email) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_blocks_name_trgm ON blocks USING gin (lower(name) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_rooms_room_code_trgm ON rooms USING gin (lower(room_code) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_rooms_room_type_trgm ON rooms USING gin (lower(room_type) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_beds_bed_label_trgm ON beds USING gin (lower(bed_label) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_invoices_invoice_no_trgm ON invoices USING gin (lower(invoice_no) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_receipts_receipt_no_trgm ON receipts USING gin (lower(receipt_no) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_payments_payment_no_trgm ON payments USING gin (lower(payment_no) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_payments_reference_trgm ON payments USING gin (lower(reference) gin_trgm_ops)",
)

DROP_INDEX_STATEMENTS = (
    "DROP INDEX IF EXISTS ix_payments_reference_trgm",
    "DROP INDEX IF EXISTS ix_payments_payment_no_trgm",
    "DROP INDEX IF EXISTS ix_receipts_receipt_no_trgm",
    "DROP INDEX IF EXISTS ix_invoices_invoice_no_trgm",
    "DROP INDEX IF EXISTS ix_beds_bed_label_trgm",
    "DROP INDEX IF EXISTS ix_rooms_room_type_trgm",
    "DROP INDEX IF EXISTS ix_rooms_room_code_trgm",
    "DROP INDEX IF EXISTS ix_blocks_name_trgm",
    "DROP INDEX IF EXISTS ix_users_email_trgm",
    "DROP INDEX IF EXISTS ix_users_full_name_trgm",
    "DROP INDEX IF EXISTS ix_tenants_status",
    "DROP INDEX IF EXISTS ix_tenants_normalized_phone",
    "DROP INDEX IF EXISTS ix_tenants_phone_trgm",
    "DROP INDEX IF EXISTS ix_tenants_email_trgm",
    "DROP INDEX IF EXISTS ix_tenants_name_trgm",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    for statement in SEARCH_INDEX_STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for statement in DROP_INDEX_STATEMENTS:
        op.execute(sa.text(statement))
