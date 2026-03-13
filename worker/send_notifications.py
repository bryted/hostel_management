from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.db import get_engine
from app.models import (
    HostelProfile,
    Invoice,
    NotificationEvent,
    NotificationOutbox,
    NotificationSettings,
    Payment,
    Receipt,
    Tenant,
)
from app.notifications.providers import EmailProvider, SmsProvider, WhatsAppProvider
from app.receipts import build_receipt_pdf

load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send queued notifications.")
    parser.add_argument("--limit", type=int, default=50, help="Max notifications to send")
    return parser.parse_args()


def get_latest_payload(session: Session, outbox_id: int) -> dict[str, Any]:
    event = (
        session.execute(
            select(NotificationEvent)
            .where(NotificationEvent.outbox_id == outbox_id)
            .order_by(NotificationEvent.event_at.desc())
        )
        .scalars()
        .first()
    )
    if event and isinstance(event.payload, dict):
        return event.payload
    return {}


def record_event(
    session: Session,
    outbox: NotificationOutbox,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    session.add(
        NotificationEvent(
            outbox_id=outbox.id,
            event_type=event_type,
            payload=payload,
        )
    )


def mark_sent(
    session: Session,
    outbox: NotificationOutbox,
    payload: dict[str, Any],
    event_type: str = "sent",
) -> None:
    outbox.status = "sent"
    outbox.sent_at = datetime.now(timezone.utc)
    outbox.scheduled_at = None
    outbox.error = None
    record_event(session, outbox, event_type, payload)


def mark_failed(
    session: Session,
    outbox: NotificationOutbox,
    payload: dict[str, Any],
    error: str,
) -> None:
    outbox.status = "failed"
    outbox.error = error
    record_event(session, outbox, "failed", {**payload, "error": error})


def mark_retry(
    session: Session,
    outbox: NotificationOutbox,
    payload: dict[str, Any],
    error: str,
    delay_seconds: int,
) -> None:
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=max(delay_seconds, 1))
    outbox.status = "queued"
    outbox.scheduled_at = retry_at
    outbox.error = error
    record_event(
        session,
        outbox,
        "retry_scheduled",
        {
            **payload,
            "error": error,
            "attempt_count": outbox.attempt_count,
            "scheduled_at": retry_at.isoformat(),
        },
    )


def handle_email(
    session: Session,
    outbox: NotificationOutbox,
    payload: dict[str, Any],
    email_provider: EmailProvider,
) -> None:
    receipt_id = payload.get("receipt_id")
    attachment = None
    if receipt_id:
        receipt = session.get(Receipt, receipt_id)
        if receipt:
            payment = session.get(Payment, receipt.payment_id)
            invoice = session.get(Invoice, payment.invoice_id) if payment else None
            tenant = session.get(Tenant, invoice.tenant_id) if invoice else None
            profile = session.execute(select(HostelProfile)).scalars().first()
            if receipt and payment and invoice and tenant:
                paid_before = session.execute(
                    select(sa.func.coalesce(sa.func.sum(Payment.amount), 0)).where(
                        Payment.invoice_id == invoice.id,
                        Payment.status != "voided",
                        Payment.id < payment.id,
                    )
                ).scalar_one()
                balance_after = float(invoice.total) - (float(paid_before) + float(payment.amount))
                pdf_bytes = build_receipt_pdf(
                    receipt,
                    payment,
                    invoice,
                    tenant,
                    received_by="System",
                    profile=profile,
                    paid_before=str(paid_before),
                    balance_after=str(balance_after),
                )
                attachment = (
                    f"{receipt.receipt_no}.pdf",
                    pdf_bytes,
                    "application/pdf",
                )
            else:
                mark_failed(
                    session,
                    outbox,
                    payload,
                    "Receipt details missing for email attachment.",
                )
                return
        else:
            mark_failed(session, outbox, payload, "Receipt not found for email.")
            return

    result = email_provider.send_message(
        to=outbox.recipient,
        subject=outbox.subject or "Receipt",
        body=outbox.body,
        attachment=attachment,
    )
    if result.ok:
        mark_sent(
            session,
            outbox,
            {
                **payload,
                "provider_id": result.provider_id,
                "channel": "email",
                "response": result.details,
                "attempt_count": outbox.attempt_count,
            },
        )
    else:
        mark_failed(
            session,
            outbox,
            {**payload, "channel": "email", "response": result.details},
            result.error or "Email send failed",
        )


def handle_whatsapp_with_fallback(
    session: Session,
    outbox: NotificationOutbox,
    payload: dict[str, Any],
    whatsapp_provider: WhatsAppProvider,
    sms_provider: SmsProvider,
) -> None:
    wa_result = whatsapp_provider.send_message(outbox.recipient, outbox.body)
    if wa_result.ok:
        mark_sent(
            session,
            outbox,
            {
                **payload,
                "provider_id": wa_result.provider_id,
                "channel": "whatsapp",
                "response": wa_result.details,
                "attempt_count": outbox.attempt_count,
            },
        )
        return

    sms_result = sms_provider.send_message(outbox.recipient, outbox.body)
    if sms_result.ok:
        mark_sent(
            session,
            outbox,
            {
                **payload,
                "provider_id": sms_result.provider_id,
                "channel": "sms",
                "whatsapp_error": wa_result.error,
                "response": sms_result.details,
                "attempt_count": outbox.attempt_count,
            },
            event_type="fallback_sms_sent",
        )
    else:
        error = f"WhatsApp failed: {wa_result.error}; SMS failed: {sms_result.error}"
        mark_failed(
            session,
            outbox,
            {
                **payload,
                "channel": "whatsapp",
                "sms_error": sms_result.error,
                "response": sms_result.details,
            },
            error,
        )


def _load_settings(session: Session) -> tuple[dict[str, str], int, int]:
    settings_row = (
        session.execute(
            select(NotificationSettings).order_by(NotificationSettings.updated_at.desc())
        )
        .scalars()
        .first()
    )
    settings: dict[str, str] = {
        "whatsapp_access_token": (os.getenv("WHATSAPP_ACCESS_TOKEN") or "").strip(),
        "whatsapp_phone_number_id": (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip(),
        "whatsapp_api_version": (os.getenv("WHATSAPP_API_VERSION") or "").strip(),
        "sms_api_url": (os.getenv("SMS_API_URL") or "").strip(),
        "sms_api_key": (os.getenv("SMS_API_KEY") or "").strip(),
        "sms_sender_id": (os.getenv("SMS_SENDER_ID") or "").strip(),
        "smtp_host": (os.getenv("SMTP_HOST") or "").strip(),
        "smtp_port": (os.getenv("SMTP_PORT") or "").strip(),
        "smtp_user": (os.getenv("SMTP_USER") or "").strip(),
        "smtp_password": (os.getenv("SMTP_PASSWORD") or "").strip(),
        "smtp_from": (os.getenv("SMTP_FROM") or "").strip(),
    }
    max_attempts = 3
    retry_delay_seconds = 300
    if settings_row:
        settings["mock_mode"] = "true" if settings_row.mock_mode else "false"
        max_attempts = int(settings_row.notification_max_attempts or 3)
        retry_delay_seconds = int(settings_row.notification_retry_delay_seconds or 300)
    else:
        settings["mock_mode"] = "false"

    # Temporary compatibility switch for legacy setups.
    raw_db_secret_flag = (os.getenv("ALLOW_DB_NOTIFICATION_SECRETS") or "").strip().lower()
    allow_db_secrets = raw_db_secret_flag in {"", "1", "true", "yes", "on"}
    if allow_db_secrets and settings_row:
        settings["whatsapp_access_token"] = settings["whatsapp_access_token"] or (settings_row.whatsapp_access_token or "")
        settings["whatsapp_phone_number_id"] = settings["whatsapp_phone_number_id"] or (
            settings_row.whatsapp_phone_number_id or ""
        )
        settings["whatsapp_api_version"] = settings["whatsapp_api_version"] or (
            settings_row.whatsapp_api_version or ""
        )
        settings["sms_api_url"] = settings["sms_api_url"] or (settings_row.sms_api_url or "")
        settings["sms_api_key"] = settings["sms_api_key"] or (settings_row.sms_api_key or "")
        settings["sms_sender_id"] = settings["sms_sender_id"] or (settings_row.sms_sender_id or "")
        settings["smtp_host"] = settings["smtp_host"] or (settings_row.smtp_host or "")
        settings["smtp_port"] = settings["smtp_port"] or (str(settings_row.smtp_port) if settings_row.smtp_port else "")
        settings["smtp_user"] = settings["smtp_user"] or (settings_row.smtp_user or "")
        settings["smtp_password"] = settings["smtp_password"] or (settings_row.smtp_password or "")
        settings["smtp_from"] = settings["smtp_from"] or (settings_row.smtp_from or "")

    return settings, max(max_attempts, 1), max(retry_delay_seconds, 1)


def _processing_stale_seconds() -> int:
    raw_value = (os.getenv("NOTIFICATION_PROCESSING_STALE_SECONDS") or "").strip()
    if not raw_value:
        return 900
    try:
        parsed = int(raw_value)
    except ValueError:
        return 900
    return max(parsed, 60)


def _requeue_stale_processing(session: Session, now: datetime, stale_seconds: int) -> int:
    stale_before = now - timedelta(seconds=max(stale_seconds, 1))
    stale_rows = (
        session.execute(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.status == "processing",
                NotificationOutbox.updated_at <= stale_before,
            )
            .order_by(NotificationOutbox.updated_at.asc(), NotificationOutbox.id.asc())
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )

    recovered = 0
    for outbox in stale_rows:
        outbox.status = "queued"
        outbox.scheduled_at = now
        outbox.error = "Recovered stale processing row"
        record_event(
            session,
            outbox,
            "processing_requeued_stale",
            {
                "stale_seconds": stale_seconds,
                "previous_updated_at": outbox.updated_at.isoformat() if outbox.updated_at else None,
                "recovered_at": now.isoformat(),
            },
        )
        recovered += 1

    return recovered


def _claim_notifications(session: Session, limit: int, now: datetime) -> list[int]:
    notifications = (
        session.execute(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.status == "queued",
                sa.or_(
                    NotificationOutbox.scheduled_at.is_(None),
                    NotificationOutbox.scheduled_at <= now,
                ),
            )
            .order_by(NotificationOutbox.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )

    claimed_ids: list[int] = []
    for outbox in notifications:
        outbox.status = "processing"
        outbox.attempt_count = int(outbox.attempt_count or 0) + 1
        outbox.error = None
        record_event(
            session,
            outbox,
            "processing_started",
            {"attempt_count": outbox.attempt_count},
        )
        claimed_ids.append(outbox.id)

    return claimed_ids


def process_notifications(limit: int) -> int:
    engine = get_engine()
    with Session(engine) as session:
        settings, max_attempts, retry_delay_seconds = _load_settings(session)

    whatsapp_provider = WhatsAppProvider(settings)
    sms_provider = SmsProvider(settings)
    email_provider = EmailProvider(settings)
    stale_seconds = _processing_stale_seconds()

    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        _requeue_stale_processing(session, now, stale_seconds)
        claimed_ids = _claim_notifications(session, limit, now)
        session.commit()

    processed = 0
    for outbox_id in claimed_ids:
        with Session(engine) as session:
            outbox = session.get(NotificationOutbox, outbox_id)
            if outbox is None or outbox.status != "processing":
                continue

            payload = get_latest_payload(session, outbox.id)
            try:
                if outbox.channel == "email":
                    handle_email(session, outbox, payload, email_provider)
                elif outbox.channel == "whatsapp":
                    handle_whatsapp_with_fallback(
                        session, outbox, payload, whatsapp_provider, sms_provider
                    )
                elif outbox.channel == "sms":
                    sms_result = sms_provider.send_message(outbox.recipient, outbox.body)
                    if sms_result.ok:
                        mark_sent(
                            session,
                            outbox,
                            {
                                **payload,
                                "provider_id": sms_result.provider_id,
                                "channel": "sms",
                                "response": sms_result.details,
                                "attempt_count": outbox.attempt_count,
                            },
                        )
                    else:
                        mark_failed(
                            session,
                            outbox,
                            {**payload, "channel": "sms", "response": sms_result.details},
                            sms_result.error or "SMS send failed",
                        )
                else:
                    mark_failed(
                        session,
                        outbox,
                        payload,
                        f"Unsupported channel: {outbox.channel}",
                    )
            except Exception as exc:
                mark_failed(session, outbox, payload, f"Unhandled send error: {exc}")

            if outbox.status == "failed" and int(outbox.attempt_count or 0) < max_attempts:
                mark_retry(
                    session,
                    outbox,
                    payload,
                    outbox.error or "Notification send failed",
                    retry_delay_seconds,
                )

            if outbox.status == "failed":
                record_event(
                    session,
                    outbox,
                    "terminal_failure",
                    {
                        **payload,
                        "attempt_count": outbox.attempt_count,
                        "max_attempts": max_attempts,
                    },
                )

            session.commit()
            processed += 1

    return processed


def main() -> None:
    args = parse_args()
    processed = process_notifications(args.limit)
    print(f"Processed {processed} notifications.")


if __name__ == "__main__":
    main()
