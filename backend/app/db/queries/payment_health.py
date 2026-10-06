"""Payment Health: the base rows the verdicts, trend, failure signals and recovery are computed from.

Nothing here decides anything. Each function returns rows of payment_attempt, payment or payment_summary for one
merchant, and app/core/health.py turns them into verdicts. Every function takes merchant_id first and every
statement filters on it.
"""

from __future__ import annotations

import sqlite3

ATTEMPT_JOIN = "FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id"


def history_starts(merchant_id: str, conn: sqlite3.Connection) -> str | None:
    """The merchant's first recorded attempt (UTC ISO), or None before any attempt exists."""
    row = conn.execute("SELECT MIN(a.created_at) FROM payment_attempt a WHERE a.merchant_id = :merchant_id", {"merchant_id": merchant_id}).fetchone()
    return row[0]


def attempt_outcomes(merchant_id: str, conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    """(created_at, outcome, channel) of every attempt created in [start, end), for bucketing by Chicago day and channel."""
    return conn.execute(
        f"SELECT a.created_at, a.outcome, p.channel {ATTEMPT_JOIN} "
        "WHERE a.merchant_id = :merchant_id AND a.created_at >= :start AND a.created_at < :end ORDER BY a.created_at, a.id",
        {"merchant_id": merchant_id, "start": start, "end": end},
    ).fetchall()


def failure_signals(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """Failed attempts created in [start, end) grouped by recorded failure code, most frequent first, then by code."""
    clauses = ["a.merchant_id = :merchant_id", "a.outcome = 'failed'", "a.created_at >= :start", "a.created_at < :end"]
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    if channel:
        clauses.append("p.channel = :channel")
        params["channel"] = channel
    return conn.execute(
        f"SELECT a.failure_code, COUNT(*) AS count {ATTEMPT_JOIN} WHERE {' AND '.join(clauses)} GROUP BY a.failure_code ORDER BY count DESC, a.failure_code",
        params,
    ).fetchall()


def recovery_cohort(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """One row per payment created in [start, end) with at least one failed attempt: what recovery is classified from."""
    clauses = ["ps.merchant_id = :merchant_id", "ps.created_at >= :start", "ps.created_at < :end", "chain.failed_attempts > 0"]
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    if channel:
        clauses.append("ps.channel = :channel")
        params["channel"] = channel
    return conn.execute(
        "SELECT ps.id, ps.amount_cents, ps.currency, ps.status, ps.succeeded_at, ps.latest_outcome, chain.first_attempt_at "
        "FROM payment_summary ps "
        "JOIN (SELECT x.payment_id, MIN(x.created_at) AS first_attempt_at, SUM(x.outcome = 'failed') AS failed_attempts "
        "      FROM payment_attempt x WHERE x.merchant_id = :merchant_id GROUP BY x.payment_id) chain ON chain.payment_id = ps.id "
        f"WHERE {' AND '.join(clauses)} ORDER BY ps.created_at, ps.id",
        params,
    ).fetchall()


def _unresolved_where(merchant_id: str, start: str, end: str, channel: str | None) -> tuple[str, dict[str, object]]:
    clauses = ["ps.merchant_id = :merchant_id", "ps.created_at >= :start", "ps.created_at < :end", "ps.status = 'failed'"]
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    if channel:
        clauses.append("ps.channel = :channel")
        params["channel"] = channel
    return " AND ".join(clauses), params


def count_unresolved(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> int:
    """Payments created in [start, end) whose derived status is failed: the Payments list's status=failed total."""
    where, params = _unresolved_where(merchant_id, start, end, channel)
    return int(conn.execute(f"SELECT COUNT(*) FROM payment_summary ps WHERE {where}", params).fetchone()[0])


def list_unresolved(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None, limit: int) -> list[sqlite3.Row]:
    """The most recently attempted unresolved payments with their latest attempt's recorded failure signal."""
    where, params = _unresolved_where(merchant_id, start, end, channel)
    return conn.execute(
        "SELECT ps.id, ps.order_reference, ps.amount_cents, ps.currency, ps.latest_attempt_at, "
        "       ps.customer_id, ps.customer_name, ps.customer_email, ps.customer_reference, "
        "       la.failure_code AS last_failure_code, "
        "       (SELECT COUNT(*) FROM payment_attempt x WHERE x.payment_id = ps.id AND x.merchant_id = ps.merchant_id) AS attempt_count "
        "FROM payment_summary ps "
        "JOIN payment_attempt la ON la.id = ps.latest_attempt_id AND la.merchant_id = ps.merchant_id "
        f"WHERE {where} ORDER BY ps.latest_attempt_at DESC, ps.id DESC LIMIT :limit",
        {**params, "limit": limit},
    ).fetchall()
