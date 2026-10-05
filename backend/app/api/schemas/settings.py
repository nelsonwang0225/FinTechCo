from __future__ import annotations

from app.api.schemas.common import ApiModel
from app.api.schemas.meta import LocationOption
from app.api.schemas.payments import NoteActor


class BusinessProfile(ApiModel):
    id: str
    name: str
    slug: str
    legal_name: str
    support_email: str
    industry: str
    timezone: str
    payout_schedule: str
    payout_schedule_label: str
    destination: str
    destination_label: str
    destination_last4: str
    destination_kind: str
    created_at: str
    locations: list[LocationOption]


class TeamMember(ApiModel):
    membership_id: str
    user: NoteActor
    email: str
    title: str
    role: str
    role_label: str
    is_active: bool
    member_since: str


class TeamResponse(ApiModel):
    members: list[TeamMember]


class ActivitySubject(ApiModel):
    kind: str  # payment | dispute | payout | export
    id: str | None
    label: str


class ActivityItem(ApiModel):
    id: str
    kind: str
    kind_label: str
    actor: NoteActor
    subject: ActivitySubject
    body: str
    created_at: str


class ActivityResponse(ApiModel):
    items: list[ActivityItem]
    page: int
    page_size: int
    total: int
