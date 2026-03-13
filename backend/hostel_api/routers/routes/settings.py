from __future__ import annotations

import os
from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AllocationEvent,
    BedEvent,
    InvoiceEvent,
    NotificationEvent,
    NotificationOutbox,
    ReceiptEvent,
    Tenant,
    User,
)
from app.notifications.providers import EmailProvider, SmsProvider, WhatsAppProvider
from app.services.auth import hash_password, validate_password_strength
from app.services.lifecycle import format_timestamp
from app.services.reservations import expire_reservations_batch
from app.services.settings import get_or_create_notification_settings, notification_settings_map
from ...deps import get_db_session, require_admin
from ...schemas import (
    ActionResponse,
    AdminResetPasswordRequest,
    AuditTrailItem,
    CreateUserRequest,
    NotificationOutboxItem,
    NotificationProviderSettingsPayload,
    NotificationQueueStatus,
    NotificationSettingsPayload,
    NotificationSettingsResponse,
    ProviderTestRequest,
    SettingsOverviewResponse,
    UpdateUserRequest,
    UserListItem,
    WorkerStatus,
)

router = APIRouter()

CASHIER_SCOPE = [
    "Dashboard",
    "Billing",
    "Tenants",
    "Beds",
]
ADMIN_SCOPE = [
    "Dashboard",
    "Onboarding",
    "Billing",
    "Tenants",
    "Beds",
    "Allocations",
    "Inventory",
    "Reports",
    "Settings",
]


def _reservation_worker_interval_minutes() -> int:
    raw = (os.getenv("RESERVATION_EXPIRY_INTERVAL_MINUTES") or "").strip()
    if not raw:
        return 5
    try:
        return max(int(raw), 1)
    except ValueError:
        return 5


def _settings_response(session: Session) -> NotificationSettingsResponse:
    settings = get_or_create_notification_settings(session)
    provider_settings = notification_settings_map(settings)
    sms_provider = SmsProvider(provider_settings)
    email_provider = EmailProvider(provider_settings)
    whatsapp_provider = WhatsAppProvider(provider_settings)
    return NotificationSettingsResponse(
        block_duplicate_payment_reference=bool(settings.block_duplicate_payment_reference),
        notification_max_attempts=int(settings.notification_max_attempts or 3),
        notification_retry_delay_seconds=int(settings.notification_retry_delay_seconds or 300),
        reservation_default_hold_hours=int(settings.reservation_default_hold_hours or 24),
        auto_approve_invoices=bool(settings.auto_approve_invoices),
        mock_mode=bool(settings.mock_mode),
        sms_configured=sms_provider.is_configured() or bool(getattr(sms_provider, "force_mock", False)),
        email_configured=email_provider.is_configured() or bool(getattr(email_provider, "force_mock", False)),
        whatsapp_configured=whatsapp_provider.is_configured() or bool(getattr(whatsapp_provider, "force_mock", False)),
        sms_api_url=settings.sms_api_url or "",
        sms_sender_id=settings.sms_sender_id or "",
        sms_api_key_set=bool(settings.sms_api_key),
        smtp_host=settings.smtp_host or "",
        smtp_port=int(settings.smtp_port) if settings.smtp_port is not None else None,
        smtp_user=settings.smtp_user or "",
        smtp_from=settings.smtp_from or "",
        smtp_password_set=bool(settings.smtp_password),
        whatsapp_phone_number_id=settings.whatsapp_phone_number_id or "",
        whatsapp_api_version=settings.whatsapp_api_version or "",
        whatsapp_access_token_set=bool(settings.whatsapp_access_token),
    )


def _recent_audit_rows(session: Session, *, limit: int = 20) -> list[AuditTrailItem]:
    audit_rows: list[tuple[str | None, str, str, str]] = []
    sources = [
        (InvoiceEvent, "invoice"),
        (ReceiptEvent, "receipt"),
        (AllocationEvent, "allocation"),
        (BedEvent, "bed"),
        (NotificationEvent, "notification"),
    ]
    for model, source in sources:
        events = session.execute(select(model).order_by(model.created_at.desc() if hasattr(model, "created_at") else model.event_at.desc()).limit(limit)).scalars().all()
        for event in events:
            when = getattr(event, "created_at", None) or getattr(event, "event_at", None)
            payload = getattr(event, "payload", None) or getattr(event, "detail_json", None) or {}
            if isinstance(payload, dict):
                detail = ", ".join(f"{key}={value}" for key, value in payload.items() if value not in (None, ""))[:220]
            else:
                detail = ""
            audit_rows.append(
                (
                    format_timestamp(when),
                    source,
                    getattr(event, "event_type", "event"),
                    detail,
                )
            )
    audit_rows.sort(key=lambda item: item[0] or "", reverse=True)
    return [
        AuditTrailItem(when=when or "-", source=source, event=event, detail=detail or "-")
        for when, source, event, detail in audit_rows[:limit]
    ]


def _notification_rows(session: Session, *, limit: int = 25) -> list[NotificationOutboxItem]:
    rows = session.execute(
        select(NotificationOutbox, Tenant)
        .outerjoin(Tenant, Tenant.id == NotificationOutbox.tenant_id)
        .order_by(NotificationOutbox.created_at.desc())
        .limit(limit)
    ).all()
    return [
        NotificationOutboxItem(
            id=int(outbox.id),
            channel=outbox.channel,
            recipient=outbox.recipient,
            subject=outbox.subject,
            status=outbox.status,
            attempt_count=int(outbox.attempt_count or 0),
            scheduled_at=format_timestamp(outbox.scheduled_at),
            sent_at=format_timestamp(outbox.sent_at),
            error=outbox.error,
            tenant_name=tenant.name if tenant is not None else None,
        )
        for outbox, tenant in rows
    ]


@router.get("/overview", response_model=SettingsOverviewResponse)
def get_settings_overview(
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> SettingsOverviewResponse:
    users = session.execute(select(User).order_by(User.is_admin.desc(), User.full_name.asc())).scalars().all()
    queue_statuses = [
        NotificationQueueStatus(status=status_name, count=int(count or 0))
        for status_name, count in session.execute(
            select(NotificationOutbox.status, sa.func.count(NotificationOutbox.id))
            .group_by(NotificationOutbox.status)
            .order_by(NotificationOutbox.status.asc())
        ).all()
    ]
    interval_minutes = _reservation_worker_interval_minutes()
    return SettingsOverviewResponse(
        settings=_settings_response(session),
        users=[
            UserListItem(
                id=int(user.id),
                email=user.email,
                full_name=user.full_name,
                is_admin=bool(user.is_admin),
                is_active=bool(user.is_active),
            )
            for user in users
        ],
        queue_statuses=queue_statuses,
        audit_rows=_recent_audit_rows(session),
        notification_rows=_notification_rows(session),
        worker_status=WorkerStatus(
            reservation_expiry_job="Scheduled worker required for auto-release of held beds.",
            interval_minutes=interval_minutes,
        ),
        cashier_scope=CASHIER_SCOPE,
        admin_scope=ADMIN_SCOPE,
    )


@router.post("/guardrails", response_model=ActionResponse)
def update_guardrails(
    payload: NotificationSettingsPayload,
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> ActionResponse:
    settings = get_or_create_notification_settings(session)
    settings.block_duplicate_payment_reference = payload.block_duplicate_payment_reference
    settings.notification_max_attempts = payload.notification_max_attempts
    settings.notification_retry_delay_seconds = payload.notification_retry_delay_seconds
    settings.reservation_default_hold_hours = payload.reservation_default_hold_hours
    settings.auto_approve_invoices = payload.auto_approve_invoices
    session.commit()
    return ActionResponse(message="Settings updated.")


@router.post("/providers", response_model=ActionResponse)
def update_provider_settings(
    payload: NotificationProviderSettingsPayload,
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> ActionResponse:
    settings = get_or_create_notification_settings(session)
    settings.mock_mode = payload.mock_mode
    settings.sms_api_url = payload.sms_api_url.strip() or None
    if payload.sms_api_key.strip():
        settings.sms_api_key = payload.sms_api_key.strip()
    settings.sms_sender_id = payload.sms_sender_id.strip() or None
    settings.smtp_host = payload.smtp_host.strip() or None
    settings.smtp_port = payload.smtp_port
    settings.smtp_user = payload.smtp_user.strip() or None
    if payload.smtp_password.strip():
        settings.smtp_password = payload.smtp_password.strip()
    settings.smtp_from = payload.smtp_from.strip() or None
    if payload.whatsapp_access_token.strip():
        settings.whatsapp_access_token = payload.whatsapp_access_token.strip()
    settings.whatsapp_phone_number_id = payload.whatsapp_phone_number_id.strip() or None
    settings.whatsapp_api_version = payload.whatsapp_api_version.strip() or None
    session.commit()
    return ActionResponse(message="Provider settings updated.")


@router.post("/providers/test", response_model=ActionResponse)
def test_provider_delivery(
    payload: ProviderTestRequest,
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> ActionResponse:
    settings = get_or_create_notification_settings(session)
    provider_settings = notification_settings_map(settings)
    channel = payload.channel.strip().lower()
    recipient = payload.recipient.strip()
    if not recipient:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recipient is required.")

    if channel == "sms":
        provider = SmsProvider(provider_settings)
        result = provider.send_message(recipient, "Hostel Ops test SMS delivery.")
    elif channel == "email":
        provider = EmailProvider(provider_settings)
        result = provider.send_message(
            to=recipient,
            subject="Hostel Ops test email",
            body="This is a test email from Hostel Ops.",
        )
    elif channel == "whatsapp":
        provider = WhatsAppProvider(provider_settings)
        result = provider.send_message(recipient, "Hostel Ops test WhatsApp delivery.")
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported channel.")

    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.error or "Provider test failed.",
        )
    return ActionResponse(message=f"{channel.upper()} test sent.")


@router.post("/notifications/{outbox_id}/retry", response_model=ActionResponse)
def retry_notification(
    outbox_id: int,
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> ActionResponse:
    outbox = session.get(NotificationOutbox, outbox_id)
    if outbox is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification item not found.")
    outbox.status = "queued"
    outbox.error = None
    outbox.scheduled_at = None
    session.commit()
    return ActionResponse(message="Notification re-queued.")


@router.post("/workers/reservations/run", response_model=ActionResponse)
def run_reservation_worker(
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> ActionResponse:
    processed = expire_reservations_batch(
        session,
        now=datetime.now(timezone.utc),
        limit=200,
    )
    session.commit()
    return ActionResponse(message=f"Reservation expiry worker processed {processed} hold(s).")


@router.post("/users", response_model=ActionResponse)
def create_user_route(
    payload: CreateUserRequest,
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> ActionResponse:
    email = payload.email.strip().lower()
    full_name = payload.full_name.strip()
    password = payload.password
    if not email or not full_name or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email, full name, and password are required.")
    ok, password_error = validate_password_strength(password)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=password_error or "Invalid password.")
    existing = session.execute(
        select(User).where(sa.func.lower(User.email) == email)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User with this email already exists.")
    user = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        is_admin=payload.is_admin,
        is_active=True,
        tenant_id=None,
    )
    session.add(user)
    session.commit()
    return ActionResponse(message="User created.", user_id=int(user.id))


@router.post("/users/{user_id}", response_model=ActionResponse)
def update_user_route(
    user_id: int,
    payload: UpdateUserRequest,
    session: Session = Depends(get_db_session),
    current_user: dict = Depends(require_admin),
) -> ActionResponse:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if int(current_user["id"]) == int(user.id) and payload.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate the current admin session.")
    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    if payload.is_active is not None:
        user.is_active = payload.is_active
    session.commit()
    return ActionResponse(message="User updated.", user_id=int(user.id))


@router.post("/users/{user_id}/reset-password", response_model=ActionResponse)
def admin_reset_user_password(
    user_id: int,
    payload: AdminResetPasswordRequest,
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> ActionResponse:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    ok, password_error = validate_password_strength(payload.password)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=password_error or "Invalid password.")
    user.password_hash = hash_password(payload.password)
    session.commit()
    return ActionResponse(message="Password reset.", user_id=int(user.id))
