from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    frontend_origin: str = "http://127.0.0.1:3000"
    session_secret_key: str = "dev-session-secret-change-me"
    session_cookie_name: str = "hostel_session"
    session_https_only: bool = False
    session_max_age_seconds: int = 60 * 60 * 8
    login_max_attempts: int = 5
    login_window_seconds: int = 60 * 10
    login_lockout_seconds: int = 60 * 15

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        extra="ignore",
    )


settings = Settings()
