"""Payment Health: attempt outcome counts, recorded failure signals and per-payment recovery buckets.

Attempt figures filter on payment_attempt.created_at, like the Attempts tab. Recovery figures are per payment over
the payment_summary view and filter on payment.created_at, like the Payments list, so an unresolved count equals the
Payments list total for status=failed over the same scope.
"""

from __future__ import annotations

import sqlite3

ATTEMPTS_FROM = (
    "FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
    "WHERE a.merchant_id = :merchant_id AND a.created_at >= :start AND a.created_at < :end"
)


def outcome_counts_by_channel(merchant_id: str, conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    """(channel, outcome, n) for attempts created in [start, end)."""
    return conn.execute(
        f"SELECT p.channel, a.outcome, COUNT(*) AS n {ATTEMPTS_FROM} GROUP BY p.channel, a.outcome ORDER BY p.channel, a.outcome",
        {"merchant_id": merchant_id, "start": start, "end": end},
    ).fetchall()


def failure_signal_counts(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """(failure_code, n) for failed attempts created in [start, end), most frequent first."""
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    channel_clause = ""
    if channel:
        channel_clause = " AND p.channel = :channel"
        params["channel"] = channel
    return conn.execute(
        f"SELECT a.failure_code, COUNT(*) AS n {ATTEMPTS_FROM} AND a.outcome = 'failed'{channel_clause} "
        "GROUP BY a.failure_code ORDER BY n DESC, a.failure_code",
        params,
    ).fetchall()


def recovery_buckets(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """(bucket, n, amount_cents) over payments created in [start, end) that have at least one failed attempt.

    recovered: a succeeded attempt exists; unresolved: derived status is failed; awaiting_retry: the latest attempt is
    pending. Each payment is counted once and its amount once, however many attempts it has.
    """
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    channel_clause = ""
    if channel:
        channel_clause = " AND ps.channel = :channel"
        params["channel"] = channel
    return conn.execute(
        "SELECT CASE WHEN ps.succeeded_attempt_id IS NOT NULL THEN 'recovered' "
        "            WHEN ps.status = 'failed' THEN 'unresolved' ELSE 'awaiting_retry' END AS bucket, "
        "       COUNT(*) AS n, COALESCE(SUM(ps.amount_cents), 0) AS amount_cents "
        "FROM payment_summary ps "
        f"WHERE ps.merchant_id = :merchant_id AND ps.created_at >= :start AND ps.created_at < :end{channel_clause} "
        "AND EXISTS (SELECT 1 FROM payment_attempt fa WHERE fa.payment_id = ps.id AND fa.merchant_id = ps.merchant_id AND fa.outcome = 'failed') "
        "GROUP BY bucket ORDER BY bucket",
        params,
    ).fetchall()
