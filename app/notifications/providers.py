from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from urllib import parse, request
from urllib.error import HTTPError

from email.message import EmailMessage
import smtplib


@dataclass
class ProviderResult:
    ok: bool
    provider_id: str | None = None
    error: str | None = None
    details: dict[str, object] | None = None


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_config(
    settings: dict[str, str],
    *,
    settings_key: str,
    env_name: str,
    allow_db_fallback: bool,
) -> str | None:
    env_value = (os.getenv(env_name) or "").strip()
    if env_value:
        return env_value
    if allow_db_fallback:
        value = (settings.get(settings_key) or "").strip()
        return value or None
    return None


def _mock_result(prefix: str) -> ProviderResult:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return ProviderResult(
        ok=True,
        provider_id=f"mock-{prefix}-{stamp}",
        details={"mock": True, "provider": prefix},
    )


def _read_error_details(exc: HTTPError) -> dict[str, object] | None:
    try:
        raw = exc.read().decode("utf-8")
    except Exception:
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        return {"response": parsed}
    except Exception:
        return {"raw": raw}


class WhatsAppProvider:
    def __init__(self, settings: dict[str, str] | None = None) -> None:
        settings = settings or {}
        allow_db_secrets = _env_flag("ALLOW_DB_NOTIFICATION_SECRETS", default=True)
        self.token = _env_config(
            settings,
            settings_key="whatsapp_access_token",
            env_name="WHATSAPP_ACCESS_TOKEN",
            allow_db_fallback=allow_db_secrets,
        )
        self.phone_number_id = _env_config(
            settings,
            settings_key="whatsapp_phone_number_id",
            env_name="WHATSAPP_PHONE_NUMBER_ID",
            allow_db_fallback=allow_db_secrets,
        )
        version = _env_config(
            settings,
            settings_key="whatsapp_api_version",
            env_name="WHATSAPP_API_VERSION",
            allow_db_fallback=allow_db_secrets,
        ) or "v18.0"
        self.api_url = f"https://graph.facebook.com/{version}/{self.phone_number_id}/messages"
        self.force_mock = _env_flag("NOTIFICATIONS_MOCK") or settings.get("mock_mode") == "true"

    def is_configured(self) -> bool:
        return bool(self.token and self.phone_number_id)

    def send_message(self, to: str, body: str) -> ProviderResult:
        if self.force_mock:
            return _mock_result("whatsapp")
        if not self.is_configured():
            return ProviderResult(ok=False, error="WhatsApp is not configured")

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.api_url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
                provider_id = None
                if isinstance(response_data, dict):
                    messages = response_data.get("messages") or []
                    if messages and isinstance(messages, list):
                        provider_id = messages[0].get("id")
                return ProviderResult(
                    ok=True,
                    provider_id=provider_id,
                    details=response_data if isinstance(response_data, dict) else None,
                )
        except HTTPError as exc:
            details = _read_error_details(exc)
            return ProviderResult(
                ok=False,
                error=f"HTTP {exc.code}: {exc.reason}",
                details=details,
            )
        except Exception as exc:
            return ProviderResult(ok=False, error=str(exc))


class SmsProvider:
    def __init__(self, settings: dict[str, str] | None = None) -> None:
        settings = settings or {}
        allow_db_secrets = _env_flag("ALLOW_DB_NOTIFICATION_SECRETS", default=True)
        self.api_url = _env_config(
            settings,
            settings_key="sms_api_url",
            env_name="SMS_API_URL",
            allow_db_fallback=allow_db_secrets,
        )
        self.api_key = _env_config(
            settings,
            settings_key="sms_api_key",
            env_name="SMS_API_KEY",
            allow_db_fallback=allow_db_secrets,
        )
        self.sender_id = _env_config(
            settings,
            settings_key="sms_sender_id",
            env_name="SMS_SENDER_ID",
            allow_db_fallback=allow_db_secrets,
        )
        self.force_mock = _env_flag("NOTIFICATIONS_MOCK") or settings.get("mock_mode") == "true"

    def is_configured(self) -> bool:
        return bool(self.api_url and self.api_key and self.sender_id)

    def _is_v2(self) -> bool:
        return "/api/v2/" in (self.api_url or "")

    def _response_ok(self, response_data: dict[str, object]) -> tuple[bool, str | None]:
        status = response_data.get("status")
        if status is not None and str(status).lower() != "success":
            message = response_data.get("message") or response_data.get("error")
            return False, str(message) if message else str(response_data)
        code = response_data.get("code")
        if code is not None and str(code).lower() not in {"ok", "200"}:
            message = response_data.get("message") or response_data.get("error")
            return False, str(message) if message else str(code)
        return True, None

    def send_message(self, to: str, body: str) -> ProviderResult:
        if self.force_mock:
            return _mock_result("sms")
        if not self.is_configured():
            return ProviderResult(ok=False, error="SMS is not configured")

        if self._is_v2():
            payload = {"sender": self.sender_id, "message": body, "recipients": [to]}
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(
                self.api_url,
                data=data,
                headers={
                    "api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
        else:
            params = {
                "action": "send-sms",
                "api_key": self.api_key,
                "to": to,
                "from": self.sender_id,
                "sms": body,
            }
            parts = parse.urlsplit(self.api_url)
            existing = dict(parse.parse_qsl(parts.query))
            existing.update(params)
            query = parse.urlencode(existing)
            url = parse.urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
            req = request.Request(url, method="GET")
        try:
            with request.urlopen(req, timeout=20) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
                provider_id = None
                if isinstance(response_data, dict):
                    ok, error = self._response_ok(response_data)
                    if not ok:
                        return ProviderResult(ok=False, error=error, details=response_data)
                    provider_id = response_data.get("id") or response_data.get("message_id")
                return ProviderResult(
                    ok=True,
                    provider_id=provider_id,
                    details=response_data if isinstance(response_data, dict) else None,
                )
        except HTTPError as exc:
            details = _read_error_details(exc)
            return ProviderResult(
                ok=False,
                error=f"HTTP {exc.code}: {exc.reason}",
                details=details,
            )
        except Exception as exc:
            return ProviderResult(ok=False, error=str(exc))


class EmailProvider:
    def __init__(self, settings: dict[str, str] | None = None) -> None:
        settings = settings or {}
        allow_db_secrets = _env_flag("ALLOW_DB_NOTIFICATION_SECRETS", default=True)
        self.host = _env_config(
            settings,
            settings_key="smtp_host",
            env_name="SMTP_HOST",
            allow_db_fallback=allow_db_secrets,
        )
        self.port = int(
            _env_config(
                settings,
                settings_key="smtp_port",
                env_name="SMTP_PORT",
                allow_db_fallback=allow_db_secrets,
            )
            or "0"
        )
        self.user = _env_config(
            settings,
            settings_key="smtp_user",
            env_name="SMTP_USER",
            allow_db_fallback=allow_db_secrets,
        )
        self.password = _env_config(
            settings,
            settings_key="smtp_password",
            env_name="SMTP_PASSWORD",
            allow_db_fallback=allow_db_secrets,
        )
        self.from_email = _env_config(
            settings,
            settings_key="smtp_from",
            env_name="SMTP_FROM",
            allow_db_fallback=allow_db_secrets,
        )
        self.force_mock = _env_flag("NOTIFICATIONS_MOCK") or settings.get("mock_mode") == "true"

    def is_configured(self) -> bool:
        return bool(self.host and self.port and self.user and self.password and self.from_email)

    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        attachment: tuple[str, bytes, str] | None = None,
    ) -> ProviderResult:
        if self.force_mock:
            return _mock_result("email")
        if not self.is_configured():
            return ProviderResult(ok=False, error="Email is not configured")

        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        if attachment:
            filename, data, mime_type = attachment
            maintype, subtype = mime_type.split("/", 1)
            message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

        try:
            with smtplib.SMTP(self.host, self.port, timeout=20) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.send_message(message)
            return ProviderResult(ok=True, provider_id="smtp")
        except Exception as exc:
            return ProviderResult(ok=False, error=str(exc))
