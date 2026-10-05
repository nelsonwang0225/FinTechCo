"""GET /api/meta: labelled enum options and the merchant's locations. No counts, no record data."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from app.api.schemas.common import Option
from app.api.schemas.meta import LocationOption, MetaResponse
from app.auth.permissions import require
from app.auth.session import Principal
from app.core.periods import DEFAULT_PRESET, PRESET_LABELS, PRESETS
from app.core.tz import REPORTING_TIMEZONE
from app.db.connection import get_conn
from app.db.queries import meta as meta_q

router = APIRouter(prefix="/api/meta", tags=["meta"])

CHANNEL_LABELS: dict[str, str] = {"website": "Website", "mobile_app": "Mobile app", "in_store": "In store"}
PAYMENT_STATUS_LABELS: dict[str, str] = {
    "succeeded": "Succeeded", "pending": "Pending", "failed": "Failed", "partially_refunded": "Partially refunded", "refunded": "Refunded",
}
ATTEMPT_OUTCOME_LABELS: dict[str, str] = {"succeeded": "Succeeded", "failed": "Failed", "pending": "Pending"}
REFUND_STATUS_LABELS: dict[str, str] = {"pending": "Pending", "succeeded": "Succeeded"}
REFUND_REASON_LABELS: dict[str, str] = {
    "requested_by_customer": "Requested by customer", "damaged_in_transit": "Damaged in transit", "wrong_item": "Wrong item",
    "duplicate": "Duplicate", "price_adjustment": "Price adjustment", "returned_in_store": "Returned in store",
}
DISPUTE_STATUS_LABELS: dict[str, str] = {"needs_response": "Needs response", "under_review": "Under review", "won": "Won", "lost": "Lost"}
DISPUTE_REASON_LABELS: dict[str, str] = {
    "fraudulent": "Fraudulent", "product_not_received": "Product not received", "product_unacceptable": "Product unacceptable",
    "duplicate": "Duplicate", "credit_not_processed": "Credit not processed",
}
PAYOUT_STATUS_LABELS: dict[str, str] = {"in_transit": "In transit", "paid": "Paid"}
METHOD_LABELS: dict[str, str] = {"card": "Card", "wallet": "Wallet"}
CARD_BRAND_LABELS: dict[str, str] = {"visa": "Visa", "mastercard": "Mastercard", "amex": "American Express", "discover": "Discover"}
WALLET_LABELS: dict[str, str] = {"apple_pay": "Apple Pay", "google_pay": "Google Pay"}


def options(labels: dict[str, str]) -> list[Option]:
    return [Option(value=value, label=label) for value, label in labels.items()]


@router.get("", response_model=MetaResponse)
def get_meta(principal: Principal = Depends(require("overview:read")), conn: sqlite3.Connection = Depends(get_conn)) -> MetaResponse:
    return MetaResponse(
        channels=options(CHANNEL_LABELS),
        payment_statuses=options(PAYMENT_STATUS_LABELS),
        attempt_outcomes=options(ATTEMPT_OUTCOME_LABELS),
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
