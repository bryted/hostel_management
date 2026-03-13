"""Add handled_by_user_id to payments.

Revision ID: 0006_payment_handled_by_user
Revises: 0005_settings_tables
Create Date: 2026-01-31 10:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0006_payment_handled_by_user"
down_revision = "0005_settings_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("handled_by_user_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_payments_handled_by_user_id_users",
        "payments",
        "users",
        ["handled_by_user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_payments_handled_by_user_id_users",
        "payments",
        type_="foreignkey",
    )
    op.drop_column("payments", "handled_by_user_id")
