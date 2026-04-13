"""add payment allocations

Revision ID: 0023_payment_allocations
Revises: 0022_academic_years
Create Date: 2026-04-13 11:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0023_payment_allocations"
down_revision = "0022_academic_years"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True, nullable=False),
        sa.Column("payment_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("academic_year_id", sa.BigInteger(), nullable=True),
        sa.Column("allocated_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("allocated_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["academic_year_id"], ["academic_years.id"], name=op.f("fk_payment_allocations_academic_year_id_academic_years")),
        sa.ForeignKeyConstraint(["allocated_by_user_id"], ["users.id"], name=op.f("fk_payment_allocations_allocated_by_user_id_users")),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], name=op.f("fk_payment_allocations_invoice_id_invoices")),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], name=op.f("fk_payment_allocations_payment_id_payments")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_payment_allocations_tenant_id_tenants")),
    )
    op.create_index("ix_payment_allocations_payment_id", "payment_allocations", ["payment_id"], unique=False)
    op.create_index("ix_payment_allocations_invoice_id", "payment_allocations", ["invoice_id"], unique=False)
    op.create_index("ix_payment_allocations_tenant_year", "payment_allocations", ["tenant_id", "academic_year_id"], unique=False)

    payment_rows = bind.execute(
        sa.text(
            """
            SELECT id, tenant_id, invoice_id, academic_year_id, handled_by_user_id, amount, paid_at, created_at
            FROM payments
            WHERE invoice_id IS NOT NULL
            """
        )
    ).mappings()
    for row in payment_rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO payment_allocations (
                    payment_id,
                    invoice_id,
                    tenant_id,
                    academic_year_id,
                    allocated_amount,
                    allocated_at,
                    allocated_by_user_id
                )
                VALUES (
                    :payment_id,
                    :invoice_id,
                    :tenant_id,
                    :academic_year_id,
                    :allocated_amount,
                    :allocated_at,
                    :allocated_by_user_id
                )
                """
            ),
            {
                "payment_id": row["id"],
                "invoice_id": row["invoice_id"],
                "tenant_id": row["tenant_id"],
                "academic_year_id": row["academic_year_id"],
                "allocated_amount": row["amount"],
                "allocated_at": row["paid_at"] or row["created_at"],
                "allocated_by_user_id": row["handled_by_user_id"],
            },
        )


def downgrade() -> None:
    op.drop_index("ix_payment_allocations_tenant_year", table_name="payment_allocations")
    op.drop_index("ix_payment_allocations_invoice_id", table_name="payment_allocations")
    op.drop_index("ix_payment_allocations_payment_id", table_name="payment_allocations")
    op.drop_table("payment_allocations")
