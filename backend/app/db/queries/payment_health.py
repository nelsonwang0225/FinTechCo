"""Payment Health: completed-attempt outcomes, recorded failure codes and the per-payment recovery cohort.

Attempt figures filter on payment_attempt.created_at (the Attempts tab's timestamp). The recovery cohort filters on
payment.created_at (the Payments list's timestamp), so the unresolved drill-down lands on the same payments.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

ATTEMPT_JOIN = "FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id"


@dataclass(frozen=True)
class HealthFilters:
    start: str  # inclusive UTC ISO
    end: str  # exclusive UTC ISO
    channel: str | None = None


def _attempt_where(merchant_id: str, f: HealthFilters) -> tuple[str, dict[str, object]]:
    clauses = ["a.merchant_id = :merchant_id", "a.created_at >= :start", "a.created_at < :end"]
    params: dict[str, object] = {"merchant_id": merchant_id, "start": f.start, "end": f.end}
    if f.channel:
        clauses.append("p.channel = :channel")
        params["channel"] = f.channel
    return " AND ".join(clauses), params


def attempt_rows(merchant_id: str, conn: sqlite3.Connection, f: HealthFilters) -> list[sqlite3.Row]:
    """created_at and outcome of every attempt in the window; totals and day buckets are both counted from these rows."""
    where, params = _attempt_where(merchant_id, f)
    return conn.execute(f"SELECT a.created_at, a.outcome {ATTEMPT_JOIN} WHERE {where} ORDER BY a.created_at, a.id", params).fetchall()


def failure_signals(merchant_id: str, conn: sqlite3.Connection, f: HealthFilters) -> list[sqlite3.Row]:
    """Failed attempts in the window grouped by their recorded failure code, most frequent first."""
    where, params = _attempt_where(merchant_id, f)
    return conn.execute(
        f"SELECT a.failure_code, COUNT(*) AS count {ATTEMPT_JOIN} WHERE {where} AND a.outcome = 'failed' "
        "GROUP BY a.failure_code ORDER BY count DESC, a.failure_code",
        params,
    ).fetchall()


def recovery_cohort(merchant_id: str, conn: sqlite3.Connection, f: HealthFilters) -> list[sqlite3.Row]:
    """One row per payment created in the window with at least one failed attempt, counted once whatever its attempts."""
    clauses = [
        "ps.merchant_id = :merchant_id",
        "ps.created_at >= :start",
        "ps.created_at < :end",
        "EXISTS (SELECT 1 FROM payment_attempt fa WHERE fa.payment_id = ps.id AND fa.merchant_id = :merchant_id AND fa.outcome = 'failed')",
    ]
    params: dict[str, object] = {"merchant_id": merchant_id, "start": f.start, "end": f.end}
    if f.channel:
        clauses.append("ps.channel = :channel")
        params["channel"] = f.channel
    return conn.execute(
        "SELECT ps.id, ps.amount_cents, ps.succeeded_attempt_id, ps.succeeded_at, ps.latest_outcome, "
        "(SELECT MIN(fa.created_at) FROM payment_attempt fa WHERE fa.payment_id = ps.id AND fa.merchant_id = :merchant_id) AS first_attempt_at "
        f"FROM payment_summary ps WHERE {' AND '.join(clauses)} ORDER BY ps.created_at, ps.id",
        params,
    ).fetchall()
