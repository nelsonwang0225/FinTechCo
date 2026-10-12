"""app.core.health: the Payment Health rules at their boundaries, over hand-written rows."""

from __future__ import annotations

from datetime import date

import pytest

from app.core import health
from app.core.health import Counts


def attempt(created_at: str, outcome: str, channel: str = "website", failure_code: str | None = None) -> dict[str, object]:
    if outcome == "failed" and failure_code is None:
        failure_code = "do_not_honor"
    return {"created_at": created_at, "outcome": outcome, "channel": channel, "failure_code": failure_code}


def counts(succeeded: int, failed: int, pending: int = 0) -> Counts:
    return Counts(succeeded=succeeded, failed=failed, pending=pending)


@pytest.mark.parametrize(
    "succeeded,completed,expected",
    [(0, 0, None), (1, 1, 10000), (0, 5, 0), (2, 3, 6667), (1, 3, 3333), (1, 8, 1250), (1, 16, 625), (1, 32, 313), (171, 186, 9194)],
)
def test_rate_is_integer_basis_points_rounded_half_up(succeeded: int, completed: int, expected: int | None) -> None:
    assert health.rate_bp(succeeded, completed) == expected


def test_pending_attempts_are_counted_but_not_in_the_rate() -> None:
    c = health.count_attempts([attempt("2026-10-01T15:00:00Z", "succeeded"), attempt("2026-10-01T15:01:00Z", "pending")])
    assert (c.succeeded, c.failed, c.pending, c.completed, c.rate_bp) == (1, 0, 1, 1, 10000)


def test_degraded_exactly_at_the_threshold_and_not_one_point_before() -> None:
    baseline = counts(900, 100)  # 9000 bp
    assert health.assess(counts(80, 20), baseline) == "degraded"  # 8000 bp: drop of exactly 1000
    assert health.assess(counts(8001, 1999), baseline) == "no_significant_degradation"  # 8001 bp: drop of 999
    assert health.assess(counts(95, 5), baseline) == "no_significant_degradation"  # better than baseline


def test_volume_minimums_gate_the_conclusion() -> None:
    low = counts(0, health.MIN_PERIOD_COMPLETED - 1)
    enough = counts(0, health.MIN_PERIOD_COMPLETED)
    baseline = counts(health.MIN_BASELINE_COMPLETED, 0)
    thin_baseline = counts(health.MIN_BASELINE_COMPLETED - 1, 0)
    assert health.assess(low, baseline) == "insufficient_volume"
    assert health.assess(enough, baseline) == "degraded"
    assert health.assess(enough, thin_baseline) == "insufficient_volume"
    assert health.assess(counts(0, 0, pending=3), baseline) == "no_completed_attempts"


@pytest.mark.parametrize(
    "assessments,expected",
    [
        (["degraded", "insufficient_volume"], "degraded"),
        (["no_significant_degradation", "insufficient_volume"], "no_significant_degradation"),
        (["insufficient_volume", "no_completed_attempts"], "insufficient_data"),
        (["no_completed_attempts"], "no_completed_attempts"),
        ([], "no_completed_attempts"),
    ],
)
def test_attention_state(assessments: list[str], expected: str) -> None:
    assert health.attention_state(assessments) == expected


def test_baseline_is_the_thirty_days_before_the_period() -> None:
    assert health.baseline_days(date(2026, 9, 29)) == (date(2026, 8, 30), date(2026, 9, 28))


def test_trend_leaves_gaps_and_marks_low_volume_days() -> None:
    days = [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)]
    # 2026-10-01 in Chicago: 05:00Z..05:00Z next day. Twelve completed on Oct 1, two on Oct 3, only a pending on Oct 2.
    rows = [attempt(f"2026-10-01T{h:02d}:00:00Z", "succeeded") for h in range(6, 18)]
    rows += [attempt("2026-10-02T15:00:00Z", "pending"), attempt("2026-10-03T15:00:00Z", "failed"), attempt("2026-10-03T16:00:00Z", "succeeded")]
    rows += [attempt("2026-10-03T17:00:00Z", "failed", channel="in_store")]
    points = health.daily_trend(rows, days, channel="website")
    assert [(p.day, p.counts.completed, p.counts.rate_bp, p.low_volume) for p in points] == [
        (date(2026, 10, 1), 12, 10000, False),
        (date(2026, 10, 2), 0, None, False),
        (date(2026, 10, 3), 2, 5000, True),
    ]
    assert points[1].counts.pending == 1


def test_days_are_chicago_calendar_days() -> None:
    # 04:30Z on Oct 2 is still Oct 1 in Chicago (CDT, UTC-5).
    points = health.daily_trend([attempt("2026-10-02T04:30:00Z", "succeeded")], [date(2026, 10, 1), date(2026, 10, 2)])
    assert [p.counts.completed for p in points] == [1, 0]
    assert health.days_with_completed([attempt("2026-10-02T04:30:00Z", "succeeded"), attempt("2026-10-02T06:00:00Z", "pending")]) == 1


def test_signals_count_failed_attempts_by_code() -> None:
    rows = [
        attempt("2026-10-01T15:00:00Z", "failed", failure_code="issuer_unavailable"),
        attempt("2026-10-01T15:01:00Z", "failed", failure_code="issuer_unavailable"),
        attempt("2026-10-01T15:02:00Z", "failed", failure_code="do_not_honor"),
        attempt("2026-10-01T15:03:00Z", "failed", failure_code="authentication_failed"),
        attempt("2026-10-01T15:04:00Z", "failed", channel="in_store", failure_code="expired_card"),
        attempt("2026-10-01T15:05:00Z", "succeeded"),
    ]
    assert health.signal_counts(rows, channel="website") == [("issuer_unavailable", 2), ("authentication_failed", 1), ("do_not_honor", 1)]
    assert sum(n for _, n in health.signal_counts(rows)) == 5


def payment(status: str, amount_cents: int, first: str = "2026-10-01T15:00:00Z", succeeded_at: str | None = None) -> dict[str, object]:
    return {"status": status, "amount_cents": amount_cents, "first_attempt_at": first, "succeeded_at": succeeded_at}


def test_recovery_counts_each_payment_once() -> None:
    rows = [
        payment("succeeded", 1000, succeeded_at="2026-10-01T16:00:00Z"),  # exactly one hour
        payment("refunded", 2000, succeeded_at="2026-10-01T16:00:01Z"),  # one second over
        payment("failed", 3000),
        payment("pending", 4000),
    ]
    r = health.recovery(rows)
    assert (r.affected.payments, r.affected.amount_cents) == (4, 10000)
    assert (r.recovered.payments, r.recovered.amount_cents) == (2, 3000)
    assert (r.recovered_within_hour.payments, r.recovered_within_hour.amount_cents) == (1, 1000)
    assert (r.unresolved.payments, r.unresolved.amount_cents) == (1, 3000)
    assert (r.in_progress.payments, r.in_progress.amount_cents) == (1, 4000)
    assert r.recovered.payments + r.unresolved.payments + r.in_progress.payments == r.affected.payments
