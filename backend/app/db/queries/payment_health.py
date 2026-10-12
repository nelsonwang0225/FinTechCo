"""Payment Health: the attempt and payment rows its figures are derived from.

Attempt figures are anchored on payment_attempt.created_at (as the Attempts tab is); recovery is per payment, anchored on
payment.created_at (as the Payments list is). Every function takes merchant_id first and every table is filtered on it.
"""

from __future__ import annotations

import sqlite3


def attempt_rows(merchant_id: str, conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    """One row per attempt created in [start, end): when, outcome, recorded failure code and the payment's channel."""
    return conn.execute(
        """
        SELECT a.created_at, a.outcome, a.failure_code, p.channel
        FROM payment_attempt a
        JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id
        WHERE a.merchant_id = :merchant_id AND a.created_at >= :start AND a.created_at < :end
        ORDER BY a.created_at, a.id
        """,
        {"merchant_id": merchant_id, "start": start, "end": end},
    ).fetchall()


def outcome_counts(merchant_id: str, conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    """Attempts created in [start, end) counted by channel and outcome."""
    return conn.execute(
        """
        SELECT p.channel, a.outcome, COUNT(*) AS n
        FROM payment_attempt a
        JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id
        WHERE a.merchant_id = :merchant_id AND a.created_at >= :start AND a.created_at < :end
        GROUP BY p.channel, a.outcome
        ORDER BY p.channel, a.outcome
        """,
        {"merchant_id": merchant_id, "start": start, "end": end},
    ).fetchall()


def affected_payments(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None = None) -> list[sqlite3.Row]:
    """Payments created in [start, end) with at least one failed attempt, one row per payment."""
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    channel_clause = ""
    if channel:
        channel_clause = "AND ps.channel = :channel"
        params["channel"] = channel
    return conn.execute(
        f"""
        SELECT ps.id, ps.created_at, ps.amount_cents, ps.currency, ps.status, ps.succeeded_attempt_id, ps.succeeded_at, ps.latest_outcome
        FROM payment_summary ps
        WHERE ps.merchant_id = :merchant_id AND ps.created_at >= :start AND ps.created_at < :end {channel_clause}
          AND EXISTS (
            SELECT 1 FROM payment_attempt a
            WHERE a.payment_id = ps.id AND a.merchant_id = :merchant_id AND a.outcome = 'failed'
          )
        ORDER BY ps.created_at, ps.id
        """,
        params,
    ).fetchall()
