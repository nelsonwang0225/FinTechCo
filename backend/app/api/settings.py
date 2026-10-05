"""Settings (business admin): the business profile, the team roster and the activity log. All read-only."""

from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.listing import page_params
from app.api.payouts import destination_string
from app.api.schemas.meta import LocationOption
from app.api.schemas.payments import NoteActor
from app.api.schemas.settings import ActivityItem, ActivityResponse, ActivitySubject, BusinessProfile, TeamMember, TeamResponse
from app.auth.permissions import require
from app.auth.session import Principal
from app.core.labels import ROLE_LABELS
from app.core.schedule import SCHEDULE_LABELS
from app.core.tz import REPORTING_TIMEZONE
from app.db.connection import get_conn
from app.db.queries import meta as meta_q
from app.db.queries import notes as notes_q
from app.db.queries import settings as settings_q
from app.db.queries.common import Page

router = APIRouter(prefix="/api/settings", tags=["settings"])

ActivityKind = Literal["note", "export"]
KIND_LABELS = {"note": "Note added", "export": "CSV exported"}


@router.get("/profile", response_model=BusinessProfile)
def get_profile(principal: Principal = Depends(require("settings:read")), conn: sqlite3.Connection = Depends(get_conn)) -> BusinessProfile:
    m = settings_q.merchant_profile(principal.merchant_id, conn)
    return BusinessProfile(
        id=m["id"],
        name=m["name"],
        slug=m["slug"],
        legal_name=m["legal_name"],
        support_email=m["support_email"],
        industry=m["industry"],
        timezone=REPORTING_TIMEZONE,
        payout_schedule=m["payout_schedule"],
        payout_schedule_label=SCHEDULE_LABELS[m["payout_schedule"]],
        destination=destination_string(m, m["name"]),
        destination_label=m["destination_label"],
        destination_last4=m["destination_last4"],
        destination_kind=m["destination_kind"],
        created_at=m["created_at"],
        locations=[LocationOption(**dict(row)) for row in meta_q.list_locations(principal.merchant_id, conn)],
    )


@router.get("/team", response_model=TeamResponse)
def get_team(principal: Principal = Depends(require("settings:read")), conn: sqlite3.Connection = Depends(get_conn)) -> TeamResponse:
    members = [
        TeamMember(
            membership_id=r["membership_id"],
            user=NoteActor(id=r["user_id"], full_name=r["full_name"]),
            email=r["email"],
            title=r["title"],
            role=r["role"],
            role_label=ROLE_LABELS[r["role"]],
            is_active=bool(r["is_active"]),
            member_since=r["created_at"],
        )
        for r in settings_q.list_team(principal.merchant_id, conn)
    ]
    return TeamResponse(members=members)


def activity_item(row: sqlite3.Row) -> ActivityItem:
    if row["payment_id"]:
        subject = ActivitySubject(kind="payment", id=row["payment_id"], label=row["payment_reference"])
    elif row["dispute_id"]:
        subject = ActivitySubject(kind="dispute", id=row["dispute_id"], label=f"Dispute on {row['dispute_reference']}")
    elif row["payout_id"]:
        subject = ActivitySubject(kind="payout", id=row["payout_id"], label=row["export_name"])
    else:
        subject = ActivitySubject(kind="export", id=None, label=row["export_name"])
    return ActivityItem(
        id=row["id"],
        kind=row["kind"],
        kind_label=KIND_LABELS[row["kind"]],
        actor=NoteActor(id=row["actor_id"], full_name=row["actor_name"]),
        subject=subject,
        body=row["body"],
        created_at=row["created_at"],
    )


@router.get("/activity", response_model=ActivityResponse)
def get_activity(
    principal: Principal = Depends(require("settings:read")),
    conn: sqlite3.Connection = Depends(get_conn),
    page: Page = Depends(page_params),
    kind: ActivityKind | None = None,
) -> ActivityResponse:
    rows, total = notes_q.list_activity(principal.merchant_id, conn, kind, page)
    return ActivityResponse(items=[activity_item(r) for r in rows], page=page.page, page_size=page.page_size, total=total)
