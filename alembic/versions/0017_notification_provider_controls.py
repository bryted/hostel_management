"""Add provider configuration controls and invoice approval toggle.

Revision ID: 0017_provider_controls
Revises: 0016_security_currency_alignment
Create Date: 2026-03-13 15:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_provider_controls"
down_revision = "0016_security_currency_alignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_settings",
        sa.Column(
            "auto_approve_invoices",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("notification_settings", "auto_approve_invoices")
