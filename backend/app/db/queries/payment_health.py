"""Payment Health: attempt outcomes and per-payment recovery for a period.

Attempt figures filter on payment_attempt.created_at, as the Attempts tab does; recovery figures take the payments created
in the period, as the Payments list does, and look at each payment's whole attempt chain. Every function takes merchant_id
first and every statement filters on it.
"""

from __future__ import annotations

import sqlite3


def _channel_clause(channel: str | None, params: dict[str, object]) -> str:
    if channel is None:
        return ""
    params["channel"] = channel
    return " AND p.channel = :channel"


def outcome_counts_by_channel(merchant_id: str, conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    """Succeeded, failed and pending attempts per channel, created in [start, end)."""
    return conn.execute(
        "SELECT p.channel, SUM(a.outcome = 'succeeded') AS succeeded, SUM(a.outcome = 'failed') AS failed, SUM(a.outcome = 'pending') AS pending "
        "FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        "WHERE a.merchant_id = :merchant_id AND a.created_at >= :start AND a.created_at < :end GROUP BY p.channel ORDER BY p.channel",
        {"merchant_id": merchant_id, "start": start, "end": end},
    ).fetchall()


def attempt_outcomes(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """created_at and outcome of every attempt in [start, end), for bucketing by Chicago day."""
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    return conn.execute(
        "SELECT a.created_at, a.outcome FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        "WHERE a.merchant_id = :merchant_id AND a.created_at >= :start AND a.created_at < :end"
        + _channel_clause(channel, params)
        + " ORDER BY a.created_at, a.id",
        params,
    ).fetchall()


def failure_signal_counts(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """Failed attempts in [start, end) grouped by recorded failure code, most frequent first."""
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    return conn.execute(
        "SELECT a.failure_code, COUNT(*) AS failed_attempts FROM payment_attempt a "
        "JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        "WHERE a.merchant_id = :merchant_id AND a.outcome = 'failed' AND a.created_at >= :start AND a.created_at < :end"
        + _channel_clause(channel, params)
        + " GROUP BY a.failure_code ORDER BY failed_attempts DESC, a.failure_code",
        params,
    ).fetchall()


def affected_payments(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """Payments created in [start, end) with at least one failed attempt, newest first (the Payments list default order).

    Each row carries the payment's whole chain summary: failed-attempt count, first attempt time, the succeeded attempt
    (if any) and the most recent failure.
    """
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    channel_sql = ""
    if channel is not None:
        params["channel"] = channel
        channel_sql = " AND ps.channel = :channel"
    return conn.execute(
        "WITH chain AS ("
        "  SELECT payment_id, SUM(outcome = 'failed') AS failed_attempts, MIN(created_at) AS first_attempt_at,"
        "         MAX(CASE WHEN outcome = 'failed' THEN attempt_number END) AS last_failed_number"
        "  FROM payment_attempt WHERE merchant_id = :merchant_id GROUP BY payment_id HAVING SUM(outcome = 'failed') > 0"
        ") "
        "SELECT ps.id, ps.order_reference, ps.created_at, ps.amount_cents, ps.currency, ps.channel, ps.status, ps.latest_outcome,"
        "       ps.succeeded_attempt_id, ps.succeeded_at, ps.customer_id, ps.customer_name, ps.customer_email, ps.customer_reference,"
        "       chain.failed_attempts, chain.first_attempt_at, lf.failure_code AS last_failure_code "
        "FROM payment_summary ps "
        "JOIN chain ON chain.payment_id = ps.id "
        "JOIN payment_attempt lf ON lf.payment_id = ps.id AND lf.merchant_id = ps.merchant_id AND lf.attempt_number = chain.last_failed_number "
        "WHERE ps.merchant_id = :merchant_id AND ps.created_at >= :start AND ps.created_at < :end" + channel_sql + " "
        "ORDER BY ps.created_at DESC, ps.id DESC",
        params,
    ).fetchall()
