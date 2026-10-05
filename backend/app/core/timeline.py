"""Derive a payment's timeline at read time from its base records. Nothing here is stored."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.core.labels import DISPUTE_REASON_LABELS, DISPUTE_STATUS_LABELS, REFUND_REASON_LABELS, method_label
from app.core.money import format_usd


@dataclass(frozen=True)
class TimelineEvent:
    kind: str
    at: str
    title: str
    detail: str | None
    upcoming: bool
    amount_cents: int | None = None
    ref_id: str | None = None


def _usd(cents: int) -> str:
    return format_usd(cents, symbol=True)


def build_timeline(
    *,
    now_iso: str,
    payment: sqlite3.Row,
    attempts: list[sqlite3.Row],
    refunds: list[sqlite3.Row],
    dispute: sqlite3.Row | None,
    charge: sqlite3.Row | None,
    notes: list[sqlite3.Row],
    channel_label: str,
) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []

    def add(kind: str, at: str, title: str, detail: str | None = None, amount_cents: int | None = None, ref_id: str | None = None) -> None:
        events.append(TimelineEvent(kind, at, title, detail, at > now_iso, amount_cents, ref_id))

    where = channel_label if not payment["location_name"] else f"{channel_label} · {payment['location_name']}"
    add("order_received", payment["created_at"], "Order received", f"{payment['order_reference']} · {where}", payment["amount_cents"])

    for a in attempts:
        method = method_label(a["method_type"], a["card_brand"], a["card_last4"], a["wallet_type"]) or "Unknown method"
        ordinal = f"Attempt {a['attempt_number']}"
        if a["outcome"] == "succeeded":
            add("attempt_succeeded", a["completed_at"], f"{ordinal} succeeded", method, payment["amount_cents"], a["id"])
        elif a["outcome"] == "failed":
            add("attempt_failed", a["completed_at"], f"{ordinal} declined", f"{a['failure_message']} · {method}", None, a["id"])
        else:
            add("attempt_pending", a["created_at"], f"{ordinal} pending", f"Awaiting the processor · {method}", None, a["id"])

    if charge is not None:
        add("funds_available", charge["available_at"], "Funds available for payout", f"{_usd(payment['amount_cents'])} collected, less fees")
        if charge["payout_id"]:
            add("payout_included", charge["cutoff_at"], "Included in payout", f"Payout {charge['payout_id']}", None, charge["payout_id"])
            if charge["payout_status"] == "paid" and charge["paid_at"]:
                add("payout_paid", charge["paid_at"], "Payout paid", "Arrived at the bank account", None, charge["payout_id"])
            elif charge["sent_at"]:
                add("payout_sent", charge["sent_at"], "Payout in transit", "Sent to the bank account", None, charge["payout_id"])

    for r in refunds:
        reason = REFUND_REASON_LABELS.get(r["reason"], r["reason"])
        if r["status"] == "succeeded":
            add("refund_succeeded", r["completed_at"], f"Refund of {_usd(r['amount_cents'])} completed", reason, -r["amount_cents"], r["id"])
        else:
            add("refund_pending", r["created_at"], f"Refund of {_usd(r['amount_cents'])} pending", reason, -r["amount_cents"], r["id"])

    if dispute is not None:
        reason = DISPUTE_REASON_LABELS.get(dispute["reason"], dispute["reason"])
        add("dispute_opened", dispute["opened_at"], "Dispute opened", f"{reason} · {_usd(dispute['amount_cents'])} withheld plus fee", -dispute["amount_cents"], dispute["id"])
        if dispute["responded_at"]:
            add("dispute_responded", dispute["responded_at"], "Evidence submitted", "Under review by the card network", None, dispute["id"])
        if dispute["resolved_at"]:
            outcome = DISPUTE_STATUS_LABELS[dispute["status"]]
            detail = "Funds reinstated" if dispute["status"] == "won" else "Funds not returned"
            add("dispute_resolved", dispute["resolved_at"], f"Dispute {outcome.lower()}", detail, dispute["amount_cents"] if dispute["status"] == "won" else None, dispute["id"])
        elif dispute["status"] == "needs_response":
            add("dispute_evidence_due", dispute["evidence_due_at"], "Evidence due", "Respond before this deadline", None, dispute["id"])

    for n in notes:
        add("note", n["created_at"], f"Note by {n['actor_name']}", n["body"], None, n["id"])

    events.sort(key=lambda e: (e.at, _ORDER.get(e.kind, 50)))
    return events


_ORDER: dict[str, int] = {
    "order_received": 0,
    "attempt_failed": 10,
    "attempt_pending": 10,
    "attempt_succeeded": 10,
    "funds_available": 20,
    "payout_included": 30,
    "payout_sent": 31,
    "payout_paid": 32,
    "refund_pending": 40,
    "refund_succeeded": 41,
    "dispute_opened": 42,
    "dispute_responded": 43,
    "dispute_resolved": 44,
    "dispute_evidence_due": 45,
    "note": 60,
}
