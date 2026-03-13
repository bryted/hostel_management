from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass(slots=True)
class LoginAttemptState:
    attempts: deque[datetime] = field(default_factory=deque)
    lock_until: datetime | None = None


class LoginAttemptLimiter:
    def __init__(self) -> None:
        self._state: dict[str, LoginAttemptState] = {}

    def _get_state(self, key: str) -> LoginAttemptState:
        return self._state.setdefault(key, LoginAttemptState())

    def _prune(self, state: LoginAttemptState, *, now: datetime, window_seconds: int) -> None:
        cutoff = now - timedelta(seconds=window_seconds)
        while state.attempts and state.attempts[0] < cutoff:
            state.attempts.popleft()
        if state.lock_until and state.lock_until <= now:
            state.lock_until = None

    def check(self, key: str, *, now: datetime, window_seconds: int) -> str | None:
        state = self._get_state(key)
        self._prune(state, now=now, window_seconds=window_seconds)
        if state.lock_until and state.lock_until > now:
            remaining = max(int((state.lock_until - now).total_seconds()), 1)
            return f"Too many failed login attempts. Try again in {remaining} seconds."
        return None

    def register_failure(
        self,
        key: str,
        *,
        now: datetime,
        max_attempts: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> str | None:
        state = self._get_state(key)
        self._prune(state, now=now, window_seconds=window_seconds)
        state.attempts.append(now)
        if len(state.attempts) >= max_attempts:
            state.lock_until = now + timedelta(seconds=lockout_seconds)
            return self.check(key, now=now, window_seconds=window_seconds)
        return None

    def reset(self, key: str) -> None:
        self._state.pop(key, None)


login_attempt_limiter = LoginAttemptLimiter()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
