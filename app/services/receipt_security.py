from __future__ import annotations

from decimal import Decimal
import hashlib
import hmac
import os
from urllib.parse import urlencode


def _secret() -> str:
    return (
        os.getenv("RECEIPT_SECURITY_SECRET")
        or os.getenv("SESSION_SECRET_KEY")
        or os.getenv("APP_SECRET_KEY")
        or "dev-receipt-secret-change-me"
    )


def get_frontend_origin() -> str:
    return (
        os.getenv("FRONTEND_ORIGIN")
        or os.getenv("PUBLIC_APP_URL")
        or os.getenv("NEXT_PUBLIC_APP_URL")
        or "http://127.0.0.1:3000"
    ).rstrip("/")


def _amount_text(amount: object) -> str:
    return str(Decimal(str(amount or 0)).quantize(Decimal("0.01")))


def _payload(*, receipt_no: str, amount: object, issued_at: str) -> str:
    return f"{receipt_no}|{_amount_text(amount)}|{issued_at}"


def _signature(*, receipt_no: str, amount: object, issued_at: str) -> str:
    digest = hmac.new(
        _secret().encode("utf-8"),
        _payload(receipt_no=receipt_no, amount=amount, issued_at=issued_at).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().upper()
    return digest[:12]


def build_receipt_verification_code(*, receipt_no: str, amount: object, issued_at: str) -> str:
    raw = _signature(receipt_no=receipt_no, amount=amount, issued_at=issued_at)
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}"


def normalize_receipt_verification_code(code: str) -> str:
    return "".join(character for character in code.upper() if character.isalnum())


def verify_receipt_verification_code(
    *,
    receipt_no: str,
    amount: object,
    issued_at: str,
    code: str,
) -> bool:
    expected = normalize_receipt_verification_code(
        build_receipt_verification_code(
            receipt_no=receipt_no,
            amount=amount,
            issued_at=issued_at,
        )
    )
    actual = normalize_receipt_verification_code(code)
    return bool(actual) and hmac.compare_digest(actual, expected)


def build_receipt_verification_url(*, receipt_no: str, code: str) -> str:
    query = urlencode({"receipt": receipt_no, "code": code})
    return f"{get_frontend_origin()}/verify/receipt?{query}"


def mask_phone_number(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(character for character in phone if character.isdigit())
    if len(digits) < 4:
        return phone
    return f"{digits[:3]}***{digits[-3:]}"
