"""Add hostel profile and notification settings.

Revision ID: 0005_settings_tables
Revises: 0004_payment_void_fields
Create Date: 2026-01-29 11:25:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0005_settings_tables"
down_revision = "0004_payment_void_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hostel_profile",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("logo", sa.LargeBinary(), nullable=True),
        sa.Column("logo_mime", sa.String(length=100), nullable=True),
        sa.Column("footer_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "notification_settings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("whatsapp_access_token", sa.Text(), nullable=True),
        sa.Column("whatsapp_phone_number_id", sa.String(length=100), nullable=True),
        sa.Column("whatsapp_api_version", sa.String(length=20), nullable=True),
        sa.Column("sms_api_url", sa.Text(), nullable=True),
        sa.Column("sms_api_key", sa.Text(), nullable=True),
        sa.Column("smtp_host", sa.String(length=255), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True),
        sa.Column("smtp_user", sa.String(length=255), nullable=True),
        sa.Column("smtp_password", sa.Text(), nullable=True),
        sa.Column("smtp_from", sa.String(length=255), nullable=True),
        sa.Column(
            "mock_mode",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("notification_settings")
    op.drop_table("hostel_profile")
