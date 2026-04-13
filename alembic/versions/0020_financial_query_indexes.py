"""add financial query indexes

Revision ID: 0020_financial_query_indexes
Revises: 0019_active_allocation_uniques
Create Date: 2026-04-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0020_financial_query_indexes"
down_revision = "0019_active_allocation_uniques"
branch_labels = None
depends_on = None


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if name not in existing:
        op.create_index(name, table_name, columns, unique=False)


def _drop_index_if_exists(name: str, table_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if name in existing:
        op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    _create_index_if_missing("ix_invoices_tenant_id_created_at", "invoices", ["tenant_id", "created_at"])
    _create_index_if_missing("ix_invoices_status_created_at", "invoices", ["status", "created_at"])
    _create_index_if_missing("ix_invoices_status_issued_at", "invoices", ["status", "issued_at"])
    _create_index_if_missing("ix_invoices_status_due_at", "invoices", ["status", "due_at"])
    _create_index_if_missing("ix_invoices_currency_status", "invoices", ["currency", "status"])

    _create_index_if_missing("ix_payments_invoice_id_paid_at", "payments", ["invoice_id", "paid_at"])
    _create_index_if_missing("ix_payments_tenant_id_paid_at", "payments", ["tenant_id", "paid_at"])
    _create_index_if_missing("ix_payments_status_paid_at", "payments", ["status", "paid_at"])
    _create_index_if_missing("ix_payments_currency_paid_at", "payments", ["currency", "paid_at"])
    _create_index_if_missing("ix_payments_reference", "payments", ["reference"])

    _create_index_if_missing("ix_receipts_payment_id_issued_at", "receipts", ["payment_id", "issued_at"])
    _create_index_if_missing("ix_receipts_tenant_id_issued_at", "receipts", ["tenant_id", "issued_at"])
    _create_index_if_missing("ix_receipts_issued_at", "receipts", ["issued_at"])


def downgrade() -> None:
    _drop_index_if_exists("ix_receipts_issued_at", "receipts")
    _drop_index_if_exists("ix_receipts_tenant_id_issued_at", "receipts")
    _drop_index_if_exists("ix_receipts_payment_id_issued_at", "receipts")

    _drop_index_if_exists("ix_payments_reference", "payments")
    _drop_index_if_exists("ix_payments_currency_paid_at", "payments")
    _drop_index_if_exists("ix_payments_status_paid_at", "payments")
    _drop_index_if_exists("ix_payments_tenant_id_paid_at", "payments")
    _drop_index_if_exists("ix_payments_invoice_id_paid_at", "payments")

    _drop_index_if_exists("ix_invoices_currency_status", "invoices")
    _drop_index_if_exists("ix_invoices_status_due_at", "invoices")
    _drop_index_if_exists("ix_invoices_status_issued_at", "invoices")
    _drop_index_if_exists("ix_invoices_status_created_at", "invoices")
    _drop_index_if_exists("ix_invoices_tenant_id_created_at", "invoices")
