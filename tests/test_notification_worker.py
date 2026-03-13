from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.models import NotificationEvent, NotificationOutbox
from worker.send_notifications import _requeue_stale_processing


def test_requeue_stale_processing_rows(factory, db_session):
    tenant = factory.create_tenant("Notif Tenant")
    now = factory.now()
    stale_updated = now - timedelta(minutes=40)

    stale = NotificationOutbox(
        tenant_id=tenant.id,
        channel="sms",
        recipient="+233000000001",
        body="stale",
        status="processing",
        attempt_count=1,
        updated_at=stale_updated,
    )
    fresh = NotificationOutbox(
        tenant_id=tenant.id,
        channel="sms",
        recipient="+233000000002",
        body="fresh",
        status="processing",
        attempt_count=1,
        updated_at=now,
    )
    db_session.add_all([stale, fresh])
    db_session.flush()

    recovered = _requeue_stale_processing(db_session, now, stale_seconds=300)
    db_session.flush()

    stale_db = db_session.get(NotificationOutbox, stale.id)
    fresh_db = db_session.get(NotificationOutbox, fresh.id)
    assert recovered == 1
    assert stale_db is not None and stale_db.status == "queued"
    assert stale_db.scheduled_at is not None
    assert fresh_db is not None and fresh_db.status == "processing"

    event_types = db_session.execute(
        select(NotificationEvent.event_type).where(NotificationEvent.outbox_id == stale.id)
    ).scalars().all()
    assert "processing_requeued_stale" in set(event_types)
