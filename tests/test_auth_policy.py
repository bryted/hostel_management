from __future__ import annotations

from datetime import datetime, timezone

from app.services.auth import validate_password_strength
from backend.hostel_api.security import LoginAttemptLimiter


def test_password_strength_policy_accepts_strong_password():
    ok, error = validate_password_strength("StrongPass1!")
    assert ok is True
    assert error is None


def test_password_strength_policy_rejects_weak_password():
    ok, error = validate_password_strength("weak")
    assert ok is False
    assert error is not None


def test_login_attempt_limiter_locks_after_threshold():
    limiter = LoginAttemptLimiter()
    now = datetime(2026, 3, 13, tzinfo=timezone.utc)
    key = "127.0.0.1:user@example.com"

    assert limiter.check(key, now=now, window_seconds=600) is None
    assert limiter.register_failure(
        key,
        now=now,
        max_attempts=2,
        window_seconds=600,
        lockout_seconds=900,
    ) is None
    locked_message = limiter.register_failure(
        key,
        now=now,
        max_attempts=2,
        window_seconds=600,
        lockout_seconds=900,
    )
    assert locked_message is not None
    assert "Too many failed login attempts" in locked_message
