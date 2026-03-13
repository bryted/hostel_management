from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NotificationSettings


def get_or_create_notification_settings(session: Session) -> NotificationSettings:
    settings = session.execute(select(NotificationSettings)).scalars().first()
    if settings is None:
        settings = NotificationSettings()
        session.add(settings)
        session.flush()
    return settings


def notification_settings_map(settings: NotificationSettings) -> dict[str, str]:
    return {
        "whatsapp_access_token": settings.whatsapp_access_token or "",
        "whatsapp_phone_number_id": settings.whatsapp_phone_number_id or "",
        "whatsapp_api_version": settings.whatsapp_api_version or "",
        "sms_api_url": settings.sms_api_url or "",
        "sms_api_key": settings.sms_api_key or "",
        "sms_sender_id": settings.sms_sender_id or "",
        "smtp_host": settings.smtp_host or "",
        "smtp_port": str(settings.smtp_port or ""),
        "smtp_user": settings.smtp_user or "",
        "smtp_password": settings.smtp_password or "",
        "smtp_from": settings.smtp_from or "",
        "mock_mode": "true" if bool(settings.mock_mode) else "false",
    }
