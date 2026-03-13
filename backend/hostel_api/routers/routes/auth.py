from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.notifications.providers import EmailProvider
from app.services.auth import (
    authenticate_user,
    build_password_reset_token,
    hash_password,
    validate_password_strength,
    verify_password_reset_token,
)
from app.services.settings import get_or_create_notification_settings, notification_settings_map
from ...config import settings
from ...deps import get_current_user, get_db_session
from ...security import login_attempt_limiter, utc_now
from ...schemas import (
    ActionResponse,
    LoginRequest,
    PasswordResetConfirmPayload,
    PasswordResetRequestPayload,
    PasswordResetRequestResponse,
    UserResponse,
)

router = APIRouter()


@router.post("/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: Session = Depends(get_db_session),
) -> UserResponse:
    username = payload.username.strip().lower()
    client_host = request.client.host if request.client else "unknown"
    limiter_key = f"{client_host}:{username}"
    blocked_message = login_attempt_limiter.check(
        limiter_key,
        now=utc_now(),
        window_seconds=settings.login_window_seconds,
    )
    if blocked_message:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=blocked_message)

    user = authenticate_user(session, payload.username, payload.password)
    if user is None:
        blocked_message = login_attempt_limiter.register_failure(
            limiter_key,
            now=utc_now(),
            max_attempts=settings.login_max_attempts,
            window_seconds=settings.login_window_seconds,
            lockout_seconds=settings.login_lockout_seconds,
        )
        if blocked_message:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=blocked_message)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
    login_attempt_limiter.reset(limiter_key)
    request.session.clear()
    request.session["user_id"] = int(user["id"])
    return UserResponse(**user)


@router.post("/logout")
def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
def me(user: dict = Depends(get_current_user)) -> UserResponse:
    return UserResponse(**user)


@router.post("/password-reset/request", response_model=PasswordResetRequestResponse)
def request_password_reset(
    payload: PasswordResetRequestPayload,
    session: Session = Depends(get_db_session),
) -> PasswordResetRequestResponse:
    normalized = payload.username.strip().lower()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username or email is required.")

    user = session.execute(
        select(User).where(sa.func.lower(User.email) == normalized, User.is_active.is_(True))
    ).scalar_one_or_none()
    generic_message = "If the account exists, a reset link has been prepared."
    if user is None:
        return PasswordResetRequestResponse(message=generic_message)

    token = build_password_reset_token(user)
    notification_settings = get_or_create_notification_settings(session)
    provider = EmailProvider(notification_settings_map(notification_settings))
    reset_url = f"{settings.frontend_origin}/reset-password?token={token}"

    if provider.is_configured() or bool(getattr(provider, "force_mock", False)):
        provider.send_message(
            to=user.email,
            subject="Password reset",
            body="\n".join(
                [
                    f"Hello {user.full_name},",
                    "",
                    "Use the link below to reset your password:",
                    reset_url,
                    "",
                    "If you did not request this change, contact an administrator.",
                ]
            ),
        )
    return PasswordResetRequestResponse(
        message=generic_message,
        reset_token=token if bool(getattr(provider, "force_mock", False)) else None,
    )


@router.post("/password-reset/confirm", response_model=ActionResponse)
def confirm_password_reset(
    payload: PasswordResetConfirmPayload,
    session: Session = Depends(get_db_session),
) -> ActionResponse:
    ok, password_error = validate_password_strength(payload.password)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=password_error or "Invalid password.")

    user = verify_password_reset_token(session, payload.token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token is invalid or expired.")

    user.password_hash = hash_password(payload.password)
    session.commit()
    return ActionResponse(message="Password reset completed.", user_id=int(user.id))
