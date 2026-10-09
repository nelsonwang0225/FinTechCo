"""GET /api/meta: labelled enum options and the merchant's locations. No counts, no record data."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from app.api.schemas.common import Option
from app.api.schemas.meta import LocationOption, MetaResponse
from app.auth.permissions import require
from app.core.labels import (
    ATTEMPT_OUTCOME_LABELS,
    CHANNEL_LABELS,
    DISPUTE_REASON_LABELS,
    DISPUTE_STATUS_LABELS,
    FAILURE_CODE_LABELS,
    PAYMENT_STATUS_LABELS,
    PAYOUT_STATUS_LABELS,
    REFUND_REASON_LABELS,
    REFUND_STATUS_LABELS,
)
from app.auth.session import Principal
from app.core.periods import DEFAULT_PRESET, PRESET_LABELS, PRESETS
from app.core.tz import REPORTING_TIMEZONE
from app.db.connection import get_conn
from app.db.queries import meta as meta_q

router = APIRouter(prefix="/api/meta", tags=["meta"])

def options(labels: dict[str, str]) -> list[Option]:
    return [Option(value=value, label=label) for value, label in labels.items()]


@router.get("", response_model=MetaResponse)
def get_meta(principal: Principal = Depends(require("overview:read")), conn: sqlite3.Connection = Depends(get_conn)) -> MetaResponse:
    return MetaResponse(
        channels=options(CHANNEL_LABELS),
        payment_statuses=options(PAYMENT_STATUS_LABELS),
        attempt_outcomes=options(ATTEMPT_OUTCOME_LABELS),
        failure_signals=options(FAILURE_CODE_LABELS),
        refund_statuses=options(REFUND_STATUS_LABELS),
        refund_reasons=options(REFUND_REASON_LABELS),
        dispute_statuses=options(DISPUTE_STATUS_LABELS),
        dispute_reasons=options(DISPUTE_REASON_LABELS),
        payout_statuses=options(PAYOUT_STATUS_LABELS),
        period_presets=[Option(value=p, label=PRESET_LABELS[p]) for p in PRESETS],
        default_period=DEFAULT_PRESET,
        locations=[LocationOption(**dict(row)) for row in meta_q.list_locations(principal.merchant_id, conn)],
        timezone=REPORTING_TIMEZONE,
    )
