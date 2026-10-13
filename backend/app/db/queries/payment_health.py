"""Payment Health: attempt outcomes by channel and day, recorded failure codes, and the payments affected by a failed attempt.

Attempt figures filter on payment_attempt.created_at (as the Attempts tab does). Affected payments filter on
payment.created_at (as the Payments list does), so drill-downs into either list reconcile. Every function takes
merchant_id first and every statement filters on it.
"""

from __future__ import annotations

import sqlite3

ATTEMPTS_FROM = "FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id"


def _channel_clause(channel: str | None, params: dict[str, object]) -> str:
    if channel is None:
        return ""
    params["channel"] = channel
    return " AND p.channel = :channel"


def outcome_counts(merchant_id: str, conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    """(channel, outcome, n) for every attempt created in [start, end)."""
    return conn.execute(
        f"SELECT p.channel, a.outcome, COUNT(*) AS n {ATTEMPTS_FROM} "
        "WHERE a.merchant_id = :merchant_id AND a.created_at >= :start AND a.created_at < :end "
        "GROUP BY p.channel, a.outcome ORDER BY p.channel, a.outcome",
        {"merchant_id": merchant_id, "start": start, "end": end},
    ).fetchall()


def attempt_outcomes(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """(created_at, outcome) per attempt, for bucketing into Chicago days in Python."""
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    where = "a.merchant_id = :merchant_id AND a.created_at >= :start AND a.created_at < :end" + _channel_clause(channel, params)
    return conn.execute(f"SELECT a.created_at, a.outcome {ATTEMPTS_FROM} WHERE {where} ORDER BY a.created_at, a.id", params).fetchall()


def failure_code_counts(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """(failure_code, n) over failed attempts created in [start, end), most frequent first."""
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    where = "a.merchant_id = :merchant_id AND a.outcome = 'failed' AND a.created_at >= :start AND a.created_at < :end" + _channel_clause(channel, params)
    return conn.execute(
        f"SELECT a.failure_code, COUNT(*) AS n {ATTEMPTS_FROM} WHERE {where} GROUP BY a.failure_code ORDER BY n DESC, a.failure_code",
        params,
    ).fetchall()


def affected_payments(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """Payments created in [start, end) with at least one failed attempt, one row each, with their first attempt time."""
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    channel_sql = ""
    if channel is not None:
        params["channel"] = channel
        channel_sql = " AND ps.channel = :channel"
    return conn.execute(
        "SELECT ps.id, ps.amount_cents, ps.currency, ps.status, ps.succeeded_attempt_id, ps.succeeded_at, ps.latest_outcome, "
        "(SELECT MIN(f.created_at) FROM payment_attempt f WHERE f.payment_id = ps.id AND f.merchant_id = :merchant_id) AS first_attempt_at "
        "FROM payment_summary ps "
        f"WHERE ps.merchant_id = :merchant_id AND ps.created_at >= :start AND ps.created_at < :end{channel_sql} "
        "AND EXISTS (SELECT 1 FROM payment_attempt x WHERE x.payment_id = ps.id AND x.merchant_id = :merchant_id AND x.outcome = 'failed') "
        "ORDER BY ps.created_at, ps.id",
        params,
    ).fetchall()
