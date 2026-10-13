"""Payment Health: attempt outcome counts, recorded failure signals and the payments affected by a failed attempt.

Attempt figures filter on payment_attempt.created_at, like the Attempts tab. The affected-payment cohort filters on
payment.created_at (which is its first attempt's created_at), like the Payments list, and follows each payment's later
attempts wherever they fall. Every function takes merchant_id first and every statement filters on it.
"""

from __future__ import annotations

import sqlite3

ATTEMPT_FROM = "FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id"


def _attempt_where(merchant_id: str, start: str, end: str, channel: str | None) -> tuple[str, dict[str, object]]:
    clauses = ["a.merchant_id = :merchant_id", "a.created_at >= :start", "a.created_at < :end"]
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    if channel:
        clauses.append("p.channel = :channel")
        params["channel"] = channel
    return " AND ".join(clauses), params


def outcome_counts(merchant_id: str, conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    """(channel, outcome, n) for attempts created in [start, end)."""
    where, params = _attempt_where(merchant_id, start, end, None)
    return conn.execute(f"SELECT p.channel, a.outcome, COUNT(*) AS n {ATTEMPT_FROM} WHERE {where} GROUP BY p.channel, a.outcome", params).fetchall()


def attempt_times(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """(created_at, outcome) per attempt, for bucketing into Chicago days."""
    where, params = _attempt_where(merchant_id, start, end, channel)
    return conn.execute(f"SELECT a.created_at, a.outcome {ATTEMPT_FROM} WHERE {where} ORDER BY a.created_at, a.id", params).fetchall()


def failure_signal_counts(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """(failure_code, n) over failed attempts created in [start, end), most frequent first."""
    where, params = _attempt_where(merchant_id, start, end, channel)
    return conn.execute(
        f"SELECT a.failure_code, COUNT(*) AS n {ATTEMPT_FROM} WHERE {where} AND a.outcome = 'failed' GROUP BY a.failure_code ORDER BY n DESC, a.failure_code",
        params,
    ).fetchall()


AFFECTED_SELECT = """
SELECT ps.id, ps.order_reference, ps.created_at, ps.amount_cents, ps.currency, ps.channel, ps.status, ps.succeeded_at,
       ps.latest_attempt_at, ps.customer_id, ps.customer_name, ps.customer_email, ps.customer_reference,
       (SELECT COUNT(*) FROM payment_attempt f WHERE f.payment_id = ps.id AND f.merchant_id = ps.merchant_id AND f.outcome = 'failed') AS failed_attempts,
       (SELECT f.failure_code FROM payment_attempt f WHERE f.payment_id = ps.id AND f.merchant_id = ps.merchant_id AND f.outcome = 'failed'
        ORDER BY f.attempt_number DESC LIMIT 1) AS last_failure_code
FROM payment_summary ps
"""


def _affected_where(merchant_id: str, start: str, end: str, channel: str | None) -> tuple[str, dict[str, object]]:
    clauses = [
        "ps.merchant_id = :merchant_id",
        "ps.created_at >= :start",
        "ps.created_at < :end",
        "EXISTS (SELECT 1 FROM payment_attempt f WHERE f.payment_id = ps.id AND f.merchant_id = ps.merchant_id AND f.outcome = 'failed')",
    ]
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    if channel:
        clauses.append("ps.channel = :channel")
        params["channel"] = channel
    return " AND ".join(clauses), params


def affected_payments(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """Payments created in [start, end) with at least one failed attempt, one row per payment."""
    where, params = _affected_where(merchant_id, start, end, channel)
    return conn.execute(f"{AFFECTED_SELECT} WHERE {where} ORDER BY ps.created_at, ps.id", params).fetchall()


def unresolved_payments(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None, limit: int) -> list[sqlite3.Row]:
    """Affected payments whose status is failed, newest first (the Payments list's default order)."""
    where, params = _affected_where(merchant_id, start, end, channel)
    return conn.execute(
        f"{AFFECTED_SELECT} WHERE {where} AND ps.status = 'failed' ORDER BY ps.created_at DESC, ps.id DESC LIMIT :limit", {**params, "limit": limit}
    ).fetchall()
