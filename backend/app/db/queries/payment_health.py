"""Payment Health: completed-attempt outcomes for a period and its baseline, and the affected-payment cohort.

Attempt figures filter on payment_attempt.created_at, exactly like the Attempts tab, so drill-downs reconcile. The
recovery cohort filters on payment.created_at, exactly like the Payments list, and returns one row per payment so a
payment's value is never counted once per attempt.
"""

from __future__ import annotations

import sqlite3

ATTEMPTS = """
FROM payment_attempt a
JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id
WHERE a.merchant_id = :merchant_id AND a.created_at >= :start AND a.created_at < :end
"""


def period_attempts(merchant_id: str, conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    """Every attempt created in [start, end) with its payment's channel; bucketed by Chicago day by the caller."""
    return conn.execute(
        f"SELECT a.created_at, a.outcome, a.failure_code, p.channel {ATTEMPTS} ORDER BY a.created_at, a.id",
        {"merchant_id": merchant_id, "start": start, "end": end},
    ).fetchall()


def outcome_counts_by_channel(merchant_id: str, conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    """(channel, outcome, n) for attempts created in [start, end); used for the baseline."""
    return conn.execute(
        f"SELECT p.channel, a.outcome, COUNT(*) AS n {ATTEMPTS} GROUP BY p.channel, a.outcome ORDER BY p.channel, a.outcome",
        {"merchant_id": merchant_id, "start": start, "end": end},
    ).fetchall()


def affected_payments(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """Payments created in [start, end) with at least one failed attempt: one row each, with how they ended up."""
    clauses = ["ps.merchant_id = :merchant_id", "ps.created_at >= :start", "ps.created_at < :end"]
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    if channel:
        clauses.append("ps.channel = :channel")
        params["channel"] = channel
    return conn.execute(
        f"""
        SELECT ps.id, ps.amount_cents, ps.channel, ps.succeeded_attempt_id, ps.succeeded_at, ps.latest_outcome, ps.status,
               first.created_at AS first_attempt_at
        FROM payment_summary ps
        JOIN payment_attempt first ON first.payment_id = ps.id AND first.merchant_id = ps.merchant_id AND first.attempt_number = 1
        WHERE {" AND ".join(clauses)}
          AND EXISTS (
              SELECT 1 FROM payment_attempt f
              WHERE f.payment_id = ps.id AND f.merchant_id = ps.merchant_id AND f.outcome = 'failed'
          )
        ORDER BY ps.created_at, ps.id
        """,
        params,
    ).fetchall()
