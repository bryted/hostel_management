"""Add tenant contact fields.

Revision ID: 0002_tenant_contact_fields
Revises: 0001_initial
Create Date: 2026-01-29 10:05:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0002_tenant_contact_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("tenants", sa.Column("phone", sa.String(length=50), nullable=True))
    op.add_column("tenants", sa.Column("room", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "room")
    op.drop_column("tenants", "phone")
    op.drop_column("tenants", "email")
