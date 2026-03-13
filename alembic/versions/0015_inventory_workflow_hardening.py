"""Inventory workflow hardening and reservation hold defaults.

Revision ID: 0015_inventory_flow
Revises: 0014_operational_hardening
Create Date: 2026-02-13 23:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_inventory_flow"
down_revision = "0014_operational_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_settings",
        sa.Column(
            "reservation_default_hold_hours",
            sa.Integer(),
            nullable=False,
            server_default="24",
        ),
    )

    bind = op.get_bind()

    invalid_bed_counts = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM rooms
            WHERE beds_count NOT IN (1, 2, 3, 4)
            """
        )
    ).scalar_one()
    if int(invalid_bed_counts or 0) > 0:
        raise RuntimeError("Cannot migrate rooms: beds_count must be between 1 and 4.")

    duplicate_rooms = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT block_id, room_code
                FROM rooms
                GROUP BY block_id, room_code
                HAVING count(*) > 1
            ) d
            """
        )
    ).scalar_one()
    if int(duplicate_rooms or 0) > 0:
        raise RuntimeError("Cannot create unique index on rooms(block_id, room_code): duplicates exist.")

    op.execute(
        """
        INSERT INTO floors (block_id, floor_label, is_active, created_at, updated_at)
        SELECT DISTINCT r.block_id, 'Unassigned', true, now(), now()
        FROM rooms r
        WHERE r.floor_id IS NULL
          AND NOT EXISTS (
              SELECT 1
              FROM floors f
              WHERE f.block_id = r.block_id
                AND f.floor_label = 'Unassigned'
          )
        """
    )
    op.execute(
        """
        UPDATE rooms r
        SET floor_id = (
            SELECT min(f.id)
            FROM floors f
            WHERE f.block_id = r.block_id
              AND f.floor_label = 'Unassigned'
        )
        WHERE r.floor_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE rooms
        SET room_type = CASE beds_count
            WHEN 1 THEN '1_IN_ROOM'
            WHEN 2 THEN '2_IN_ROOM'
            WHEN 3 THEN '3_IN_ROOM'
            WHEN 4 THEN '4_IN_ROOM'
            ELSE room_type
        END
        """
    )

    op.alter_column(
        "rooms",
        "floor_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.alter_column(
        "rooms",
        "room_type",
        existing_type=sa.String(length=50),
        nullable=False,
    )

    op.create_check_constraint(
        "ck_rooms_room_type_allowed",
        "rooms",
        "room_type IN ('1_IN_ROOM','2_IN_ROOM','3_IN_ROOM','4_IN_ROOM')",
    )
    op.create_check_constraint(
        "ck_rooms_beds_count_range",
        "rooms",
        "beds_count BETWEEN 1 AND 4",
    )
    op.create_check_constraint(
        "ck_rooms_room_type_beds_count_match",
        "rooms",
        """
        (room_type = '1_IN_ROOM' AND beds_count = 1) OR
        (room_type = '2_IN_ROOM' AND beds_count = 2) OR
        (room_type = '3_IN_ROOM' AND beds_count = 3) OR
        (room_type = '4_IN_ROOM' AND beds_count = 4)
        """,
    )

    op.create_index(
        "uq_rooms_block_room_code",
        "rooms",
        ["block_id", "room_code"],
        unique=True,
    )
    op.create_index(
        "ix_bed_reservations_status_expires_at",
        "bed_reservations",
        ["status", "expires_at"],
    )
    op.create_index(
        "ix_beds_room_id_status",
        "beds",
        ["room_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_beds_room_id_status", table_name="beds")
    op.drop_index("ix_bed_reservations_status_expires_at", table_name="bed_reservations")
    op.drop_index("uq_rooms_block_room_code", table_name="rooms")

    op.drop_constraint("ck_rooms_room_type_beds_count_match", "rooms", type_="check")
    op.drop_constraint("ck_rooms_beds_count_range", "rooms", type_="check")
    op.drop_constraint("ck_rooms_room_type_allowed", "rooms", type_="check")

    op.alter_column(
        "rooms",
        "room_type",
        existing_type=sa.String(length=50),
        nullable=True,
    )
    op.alter_column(
        "rooms",
        "floor_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )

    op.drop_column("notification_settings", "reservation_default_hold_hours")
