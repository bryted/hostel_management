from __future__ import annotations

from app.services.inventory import room_bed_integrity_rows


def test_integrity_flags_reserved_orphan_occupied_orphan_and_type_mismatch(factory, db_session):
    block = factory.create_block("Integrity-Block")
    floor = factory.create_floor(block, "Integrity-F1")
    room_orphan = factory.create_room(
        block,
        floor,
        room_code="INT-101",
        room_type="2_IN_ROOM",
        beds_count=2,
    )
    factory.create_bed(room_orphan, 1, status="RESERVED")
    factory.create_bed(room_orphan, 2, status="OCCUPIED")

    room_mismatch = factory.create_room(
        block,
        floor,
        room_code="INT-102",
        room_type="2_IN_ROOM",
        beds_count=2,
    )
    # Leave configured beds_count at 2 but create one bed to trigger beds_count mismatch.
    factory.create_bed(room_mismatch, 1, status="AVAILABLE")

    rows = room_bed_integrity_rows(db_session)
    orphan_row = next(item for item in rows if item["Room"] == room_orphan.room_code)
    mismatch_row = next(item for item in rows if item["Room"] == room_mismatch.room_code)

    assert orphan_row["Status"] == "CHECK"
    orphan_issues = orphan_row["Issues"]
    assert "reserved without active reservation" in orphan_issues
    assert "occupied without confirmed allocation" in orphan_issues

    assert mismatch_row["Status"] == "CHECK"
    issues = mismatch_row["Issues"]
    assert "beds_count mismatch" in issues
