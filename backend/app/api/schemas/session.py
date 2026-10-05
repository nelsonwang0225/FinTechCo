from __future__ import annotations

from app.api.schemas.common import ApiModel


class SessionUser(ApiModel):
    id: str
    full_name: str
    email: str
    title: str


class SessionMerchant(ApiModel):
    id: str
    name: str
    slug: str


class SessionResponse(ApiModel):
    membership_id: str
    user: SessionUser
    merchant: SessionMerchant
    role: str
    role_label: str
    permissions: list[str]
    as_of: str
    timezone: str


class PersonaOption(ApiModel):
    membership_id: str
    user_id: str
    full_name: str
    title: str
    role: str
    role_label: str


class PersonaMerchant(ApiModel):
    merchant: SessionMerchant
    personas: list[PersonaOption]


class PersonasResponse(ApiModel):
    merchants: list[PersonaMerchant]


class DevSessionRequest(ApiModel):
    user_id: str
    merchant_id: str
