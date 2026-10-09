"""Payment Health: attempt outcome counts, daily attempt rows, recorded failure signals and affected payments.

Attempt figures filter on payment_attempt.created_at (as the Attempts tab does); payment figures filter on
payment.created_at (as the Payments list does). Channel always comes from the payment. Every function takes
merchant_id first and every statement filters on it, including correlated subqueries.
"""

from __future__ import annotations

import sqlite3

ATTEMPTS = "FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id"


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
    return conn.execute(f"SELECT p.channel, a.outcome, COUNT(*) AS n {ATTEMPTS} WHERE {where} GROUP BY p.channel, a.outcome", params).fetchall()


def attempt_rows(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """(created_at, outcome) per attempt, for bucketing by Chicago day."""
    where, params = _attempt_where(merchant_id, start, end, channel)
    return conn.execute(f"SELECT a.created_at, a.outcome {ATTEMPTS} WHERE {where} ORDER BY a.created_at, a.id", params).fetchall()


def failure_code_counts(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """(failure_code, n) over failed attempts, most frequent first."""
    where, params = _attempt_where(merchant_id, start, end, channel)
    return conn.execute(
        f"SELECT a.failure_code, COUNT(*) AS n {ATTEMPTS} WHERE {where} AND a.outcome = 'failed' GROUP BY a.failure_code ORDER BY n DESC, a.failure_code",
        params,
    ).fetchall()


def affected_payments(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """Payments created in [start, end) with at least one failed attempt, with what recovery needs to know."""
    clauses = [
        "ps.merchant_id = :merchant_id",
        "ps.created_at >= :start",
        "ps.created_at < :end",
        "EXISTS (SELECT 1 FROM payment_attempt f WHERE f.payment_id = ps.id AND f.merchant_id = :merchant_id AND f.outcome = 'failed')",
    ]
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    if channel:
        clauses.append("ps.channel = :channel")
        params["channel"] = channel
    return conn.execute(
        "SELECT ps.id, ps.amount_cents, ps.status, ps.succeeded_attempt_id, ps.succeeded_at, "
        "(SELECT MIN(fa.created_at) FROM payment_attempt fa WHERE fa.payment_id = ps.id AND fa.merchant_id = :merchant_id) AS first_attempt_at "
        f"FROM payment_summary ps WHERE {' AND '.join(clauses)} ORDER BY ps.created_at, ps.id",
        params,
    ).fetchall()
