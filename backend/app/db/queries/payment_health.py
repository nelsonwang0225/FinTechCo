"""Payment Health: attempt outcomes, recorded failure signals and affected payments for one merchant.

Every function takes merchant_id first and every statement, subquery included, filters on it. Attempts are placed in a
period by payment_attempt.created_at (the Attempts tab's timestamp); affected payments by payment.created_at (the
Payments list's timestamp), so each drill-down opens exactly the rows a figure was computed from.
"""

from __future__ import annotations

import sqlite3

ATTEMPTS_FROM = "FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id"


def _attempt_where(channel: str | None) -> str:
    where = "a.merchant_id = :merchant_id AND a.created_at >= :start AND a.created_at < :end"
    return f"{where} AND p.channel = :channel" if channel else where


def attempt_counts_by_channel(merchant_id: str, conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    """(channel, outcome, attempts) for attempts created in [start, end)."""
    return conn.execute(
        f"SELECT p.channel, a.outcome, COUNT(*) AS attempts {ATTEMPTS_FROM} WHERE {_attempt_where(None)} GROUP BY p.channel, a.outcome",
        {"merchant_id": merchant_id, "start": start, "end": end},
    ).fetchall()


def attempt_outcomes(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """(created_at, outcome) of every attempt created in [start, end): the rows the daily trend is bucketed from."""
    return conn.execute(
        f"SELECT a.created_at, a.outcome {ATTEMPTS_FROM} WHERE {_attempt_where(channel)} ORDER BY a.created_at, a.id",
        {"merchant_id": merchant_id, "start": start, "end": end, "channel": channel},
    ).fetchall()


def failure_signals(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """(failure_code, attempts, payments) over failed attempts created in [start, end), most frequent first."""
    return conn.execute(
        f"SELECT a.failure_code, COUNT(*) AS attempts, COUNT(DISTINCT a.payment_id) AS payments {ATTEMPTS_FROM} "
        f"WHERE {_attempt_where(channel)} AND a.outcome = 'failed' GROUP BY a.failure_code ORDER BY attempts DESC, a.failure_code",
        {"merchant_id": merchant_id, "start": start, "end": end, "channel": channel},
    ).fetchall()


def affected_payments(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """One row per payment created in [start, end) with at least one failed attempt, with what became of it."""
    channel_clause = " AND p.channel = :channel" if channel else ""
    return conn.execute(
        "SELECT p.id, p.amount_cents, p.currency, p.channel, p.created_at, "
        "(SELECT COUNT(*) FROM payment_attempt f WHERE f.payment_id = p.id AND f.merchant_id = :merchant_id AND f.outcome = 'failed') "
        "AS failed_attempts, "
        "(SELECT a1.created_at FROM payment_attempt a1 WHERE a1.payment_id = p.id AND a1.merchant_id = :merchant_id "
        "ORDER BY a1.attempt_number LIMIT 1) AS first_attempt_at, "
        "(SELECT s.completed_at FROM payment_attempt s WHERE s.payment_id = p.id AND s.merchant_id = :merchant_id AND s.outcome = 'succeeded') "
        "AS succeeded_at, "
        "(SELECT la.outcome FROM payment_attempt la WHERE la.payment_id = p.id AND la.merchant_id = :merchant_id "
        "ORDER BY la.attempt_number DESC LIMIT 1) AS latest_outcome "
        "FROM payment p "
        f"WHERE p.merchant_id = :merchant_id AND p.created_at >= :start AND p.created_at < :end{channel_clause} "
        "AND EXISTS (SELECT 1 FROM payment_attempt x WHERE x.payment_id = p.id AND x.merchant_id = :merchant_id AND x.outcome = 'failed') "
        "ORDER BY p.created_at, p.id",
        {"merchant_id": merchant_id, "start": start, "end": end, "channel": channel},
    ).fetchall()
