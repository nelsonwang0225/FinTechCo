"""Development-only persona selector. Registered only when FINTECHCO_ENV != production."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Response

from app.api.schemas.session import DevSessionRequest, PersonaMerchant, PersonaOption, PersonasResponse, SessionMerchant, SessionResponse
from app.api.session import session_response
from app.auth.permissions import ROLE_LABELS
from app.auth.session import principal_from_row, set_session_cookie
from app.db.connection import get_conn
from app.db.queries import access
from app.main import ApiError

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.get("/personas", response_model=PersonasResponse)
def list_personas(conn: sqlite3.Connection = Depends(get_conn)) -> PersonasResponse:
    groups: dict[str, PersonaMerchant] = {}
    for row in access.list_personas(conn):
        group = groups.get(row["merchant_id"])
        if group is None:
            group = PersonaMerchant(merchant=SessionMerchant(id=row["merchant_id"], name=row["merchant_name"], slug=row["merchant_slug"]), personas=[])
            groups[row["merchant_id"]] = group
        group.personas.append(PersonaOption(membership_id=row["membership_id"], user_id=row["user_id"], full_name=row["user_name"],
                                            title=row["user_title"], role=row["role"], role_label=ROLE_LABELS[row["role"]]))
    return PersonasResponse(merchants=list(groups.values()))


@router.post("/session", response_model=SessionResponse)
def start_session(body: DevSessionRequest, response: Response, conn: sqlite3.Connection = Depends(get_conn)) -> SessionResponse:
    row = access.membership_for(conn, body.user_id, body.merchant_id)
    if row is None:
        raise ApiError(403, "no_membership", "That user is not a member of that business.")
    principal = principal_from_row(row)
    set_session_cookie(response, principal.membership_id)
    return session_response(principal, conn)
