"""GET/DELETE /api/session: who am I, and sign out. These depend on the principal directly (401 only)."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Response, status

from app.api.schemas.session import SessionMerchant, SessionResponse, SessionUser
from app.auth.permissions import ROLE_LABELS, permissions_for
from app.auth.session import Principal, clear_session_cookie, current_principal
from app.core import clock
from app.core.tz import REPORTING_TIMEZONE, to_iso
from app.db.connection import get_conn

router = APIRouter(prefix="/api/session", tags=["session"])


def session_response(principal: Principal, conn: sqlite3.Connection) -> SessionResponse:
    return SessionResponse(
        membership_id=principal.membership_id,
        user=SessionUser(id=principal.user_id, full_name=principal.user_name, email=principal.user_email, title=principal.user_title),
        merchant=SessionMerchant(id=principal.merchant_id, name=principal.merchant_name, slug=principal.merchant_slug),
        role=principal.role,
        role_label=ROLE_LABELS[principal.role],
        permissions=permissions_for(principal.role),
        as_of=to_iso(clock.now(conn)),
        timezone=REPORTING_TIMEZONE,
    )


@router.get("", response_model=SessionResponse)
def get_session(principal: Principal = Depends(current_principal), conn: sqlite3.Connection = Depends(get_conn)) -> SessionResponse:
    return session_response(principal, conn)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_session(response: Response) -> Response:
    out = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(out)
    return out
