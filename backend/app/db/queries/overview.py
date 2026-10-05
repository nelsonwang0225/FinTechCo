"""Overview: period totals from the ledger, the daily collected series, recent payments, the upcoming payout and attention items.

Every function here is a sum or a listing over base records. The attention queries read disputes, payouts and refunds
only; nothing in this module reads attempt rows.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from app.core.tz import chicago_day
from app.db.queries.payouts import BUCKET_TYPES


def ledger_sum(merchant_id: str, conn: sqlite3.Connection, movement_type: str, start: str, end: str) -> int:
    """Signed cents of one movement type posted in [start, end)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM balance_movement "
        "WHERE merchant_id = :merchant_id AND type = :type AND posted_at >= :start AND posted_at < :end",
        {"merchant_id": merchant_id, "type": movement_type, "start": start, "end": end},
    ).fetchone()
    return int(row[0])


def charges_posted(merchant_id: str, conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    """Every charge movement posted in [start, end): the rows the chart is bucketed from."""
    return conn.execute(
        "SELECT posted_at, amount_cents FROM balance_movement "
        "WHERE merchant_id = :merchant_id AND type = 'charge' AND posted_at >= :start AND posted_at < :end "
        "ORDER BY posted_at, id",
        {"merchant_id": merchant_id, "start": start, "end": end},
    ).fetchall()


def bucket_by_chicago_day(rows: Iterable[Mapping[str, Any]], days: list[date]) -> dict[date, int]:
    """Sum `amount_cents` per America/Chicago calendar day of `posted_at`, with a zero for every day given."""
    totals = {day: 0 for day in days}
    for row in rows:
        day = chicago_day(row["posted_at"])
        if day in totals:
            totals[day] += int(row["amount_cents"])
    return totals


def recent_payments(merchant_id: str, conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT ps.* FROM payment_summary ps WHERE ps.merchant_id = :merchant_id ORDER BY ps.created_at DESC, ps.id LIMIT :limit",
        {"merchant_id": merchant_id, "limit": limit},
    ).fetchall()


def available_buckets(merchant_id: str, conn: sqlite3.Connection, now_iso: str) -> dict[str, int]:
    """Signed cents per bucket over unswept movements available at `now`: what the next payout would carry."""
    by_type = {
        row[0]: int(row[1])
        for row in conn.execute(
            "SELECT type, SUM(amount_cents) FROM balance_movement "
            "WHERE merchant_id = :merchant_id AND payout_id IS NULL AND available_at <= :now GROUP BY type",
            {"merchant_id": merchant_id, "now": now_iso},
        )
    }
    return {bucket: sum(by_type.get(t, 0) for t in types) for bucket, types in BUCKET_TYPES.items()}


def disputes_awaiting_response(merchant_id: str, conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT d.id, d.amount_cents, d.currency, d.evidence_due_at, d.payment_id, p.order_reference "
        "FROM dispute d JOIN payment p ON p.id = d.payment_id AND p.merchant_id = d.merchant_id "
        "WHERE d.merchant_id = :merchant_id AND d.status = 'needs_response' ORDER BY d.evidence_due_at, d.id",
        {"merchant_id": merchant_id},
    ).fetchall()


def payouts_in_transit(merchant_id: str, conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, amount_cents, currency, sent_at, expected_arrival_date FROM payout "
        "WHERE merchant_id = :merchant_id AND status = 'in_transit' ORDER BY cutoff_at DESC, id",
        {"merchant_id": merchant_id},
    ).fetchall()


def refunds_pending(merchant_id: str, conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT r.id, r.amount_cents, r.currency, r.created_at, r.payment_id, p.order_reference "
        "FROM refund r JOIN payment p ON p.id = r.payment_id AND p.merchant_id = r.merchant_id "
        "WHERE r.merchant_id = :merchant_id AND r.status = 'pending' ORDER BY r.created_at DESC, r.id",
        {"merchant_id": merchant_id},
    ).fetchall()
