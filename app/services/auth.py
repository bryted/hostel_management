from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import time
from typing import Any

import sqlalchemy as sa
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User

PASSWORD_MIN_LENGTH = 10
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DEFAULT_RESET_TTL_SECONDS = 60 * 30


def _reset_secret() -> bytes:
    secret = (os.getenv("SESSION_SECRET_KEY") or os.getenv("PASSWORD_RESET_SECRET") or "dev-password-reset-secret-change-me").strip()
    return secret.encode("utf-8")


def validate_password_strength(password: str) -> tuple[bool, str | None]:
    if len(password or "") < PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if not re.search(r"[A-Z]", password):
        return False, "Password must include an uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must include a lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must include a digit."
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Password must include a symbol."
    return True, None


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        return False


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def serialize_user(user: User) -> dict[str, Any]:
    return {
        "id": int(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "is_admin": bool(user.is_admin),
        "tenant_id": int(user.tenant_id) if user.tenant_id is not None else None,
    }


def authenticate_user(session: Session, username: str, password: str) -> dict[str, Any] | None:
    normalized = (username or "").strip().lower()
    if not normalized or not password:
        return None
    user = session.execute(
        select(User).where(sa.func.lower(User.email) == normalized, User.is_active.is_(True))
    ).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return serialize_user(user)


def build_password_reset_token(user: User, *, ttl_seconds: int = DEFAULT_RESET_TTL_SECONDS) -> str:
    expires_at = int(time.time()) + max(ttl_seconds, 60)
    payload = f"{int(user.id)}:{user.email.lower()}:{expires_at}"
    signature = hmac.new(_reset_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("utf-8")


def verify_password_reset_token(session: Session, token: str) -> User | None:
    if not token:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        user_id_text, email, expires_at_text, provided_signature = decoded.split(":", 3)
        expected_payload = f"{int(user_id_text)}:{email.lower()}:{int(expires_at_text)}"
    except Exception:
        return None

    expected_signature = hmac.new(
        _reset_secret(),
        expected_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, provided_signature):
        return None
    if int(expires_at_text) < int(time.time()):
        return None

    user = session.get(User, int(user_id_text))
    if user is None or not bool(user.is_active) or user.email.lower() != email.lower():
        return None
    return user
