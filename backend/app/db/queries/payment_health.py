"""Payment Health: completed-attempt counts, recorded failure signals and per-payment recovery.

Two populations, each on the timestamp its drill-down list filters on:
- attempts whose payment_attempt.created_at is in [start, end) (the Attempts tab);
- payments whose payment.created_at is in [start, end) that have at least one failed attempt (the Payments list).

Every function takes merchant_id first and every statement, including subqueries, filters on it.
"""

from __future__ import annotations

import sqlite3

ATTEMPTS_FROM = """
FROM payment_attempt a
JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id
WHERE a.merchant_id = :merchant_id AND a.created_at >= :start AND a.created_at < :end
"""


def _channel_clause(channel: str | None, column: str) -> str:
    return f" AND {column} = :channel" if channel else ""


def attempt_outcomes_by_channel(merchant_id: str, conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    """(channel, outcome, attempts) for every attempt created in the window, across all channels."""
    return conn.execute(
        f"SELECT p.channel, a.outcome, COUNT(*) AS attempts {ATTEMPTS_FROM} GROUP BY p.channel, a.outcome ORDER BY p.channel, a.outcome",
        {"merchant_id": merchant_id, "start": start, "end": end},
    ).fetchall()


def attempt_outcome_times(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """(created_at, outcome) per attempt, for bucketing into Chicago days in Python."""
    return conn.execute(
        f"SELECT a.created_at, a.outcome {ATTEMPTS_FROM}{_channel_clause(channel, 'p.channel')} ORDER BY a.created_at, a.id",
        {"merchant_id": merchant_id, "start": start, "end": end, "channel": channel},
    ).fetchall()


def failure_signal_counts(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """(failure_code, attempts) over failed attempts in the window, most frequent first."""
    return conn.execute(
        f"SELECT a.failure_code, COUNT(*) AS attempts {ATTEMPTS_FROM} AND a.outcome = 'failed'{_channel_clause(channel, 'p.channel')} "
        "GROUP BY a.failure_code ORDER BY attempts DESC, a.failure_code",
        {"merchant_id": merchant_id, "start": start, "end": end, "channel": channel},
    ).fetchall()


def affected_payments(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """Payments created in the window with at least one failed attempt, oldest first, with what recovery needs.

    first_attempt_at is the earliest attempt's created_at; succeeded_at is the succeeded attempt's completed_at (NULL
    when none); status is the derived payment status from payment_summary.
    """
    return conn.execute(
        f"""
        SELECT ps.id, ps.order_reference, ps.amount_cents, ps.currency, ps.channel, ps.created_at, ps.status,
               ps.succeeded_attempt_id, ps.succeeded_at, ps.latest_outcome,
               ps.customer_id, ps.customer_name, ps.customer_email, ps.customer_reference,
               (SELECT MIN(f.created_at) FROM payment_attempt f
                 WHERE f.payment_id = ps.id AND f.merchant_id = :merchant_id) AS first_attempt_at,
               (SELECT COUNT(*) FROM payment_attempt n
                 WHERE n.payment_id = ps.id AND n.merchant_id = :merchant_id) AS attempt_count,
               (SELECT x.failure_code FROM payment_attempt x
                 WHERE x.payment_id = ps.id AND x.merchant_id = :merchant_id AND x.outcome = 'failed'
                 ORDER BY x.attempt_number DESC LIMIT 1) AS last_failure_code
        FROM payment_summary ps
        WHERE ps.merchant_id = :merchant_id AND ps.created_at >= :start AND ps.created_at < :end{_channel_clause(channel, 'ps.channel')}
          AND EXISTS (SELECT 1 FROM payment_attempt e
                      WHERE e.payment_id = ps.id AND e.merchant_id = :merchant_id AND e.outcome = 'failed')
        ORDER BY ps.created_at, ps.id
        """,
        {"merchant_id": merchant_id, "start": start, "end": end, "channel": channel},
    ).fetchall()
