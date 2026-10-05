"""Signed session cookie and the principal it resolves to.

The cookie carries only a membership id plus issue and expiry times, signed
with HMAC-SHA256 (stdlib only). Every request re-reads the membership row,
so nothing the client sends can carry a different merchant or role.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sqlite3
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request, Response

from app.core import clock, config
from app.db.connection import get_conn
from app.db.queries import access
from app.main import ApiError

COOKIE_NAME = "ftc_session"
SESSION_TTL = timedelta(hours=12)


@dataclass(frozen=True)
class Principal:
    membership_id: str
    user_id: str
    user_name: str
    user_email: str
    user_title: str
    merchant_id: str
    merchant_name: str
    merchant_slug: str
    role: str


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str) -> str:
    return _b64(hmac.new(config.session_secret(), payload.encode("ascii"), hashlib.sha256).digest())


def encode_token(membership_id: str, issued_at: int, expires_at: int) -> str:
    payload = _b64(json.dumps({"membership_id": membership_id, "iat": issued_at, "exp": expires_at}, separators=(",", ":")).encode())
    return f"{payload}.{_sign(payload)}"


def decode_token(token: str) -> str | None:
    """Return the membership id of a well-formed, correctly signed, unexpired token; otherwise None."""
    try:
        payload, signature = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        claims = json.loads(_unb64(payload))
    except (ValueError, UnicodeDecodeError):
        return None
    membership_id = claims.get("membership_id") if isinstance(claims, dict) else None
    expires_at = claims.get("exp") if isinstance(claims, dict) else None
    if not isinstance(membership_id, str) or not isinstance(expires_at, int):
        return None
    if int(clock.wall_now().timestamp()) >= expires_at:
        return None
    return membership_id


def set_session_cookie(response: Response, membership_id: str) -> None:
    issued = int(clock.wall_now().timestamp())
    token = encode_token(membership_id, issued, issued + int(SESSION_TTL.total_seconds()))
    response.set_cookie(COOKIE_NAME, token, max_age=int(SESSION_TTL.total_seconds()), httponly=True, samesite="lax", path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def principal_from_row(row: sqlite3.Row) -> Principal:
    return Principal(
        membership_id=row["membership_id"],
        user_id=row["user_id"],
        user_name=row["user_name"],
        user_email=row["user_email"],
        user_title=row["user_title"],
        merchant_id=row["merchant_id"],
        merchant_name=row["merchant_name"],
        merchant_slug=row["merchant_slug"],
        role=row["role"],
    )


def current_principal(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> Principal:
    token = request.cookies.get(COOKIE_NAME)
    membership_id = decode_token(token) if token else None
    if membership_id is None:
        raise ApiError(401, "unauthenticated", "Sign in to continue.")
    row = access.principal_row(conn, membership_id)
    if row is None or not row["is_active"]:
        raise ApiError(401, "unauthenticated", "Sign in to continue.")
    return principal_from_row(row)
