"""Payment Health rule: completed-attempt rates, the volume guard, the exact 10-point boundary and labels."""

from __future__ import annotations

from datetime import date

import pytest

from app.core import health_rules as rules
from app.core.health_rules import OutcomeCounts
from app.core.labels import FAILURE_CODE_LABELS
from app.seed import scenario


def test_rate_ignores_pending_and_is_none_without_completed_attempts() -> None:
    assert rules.rate_bp(OutcomeCounts(succeeded=3, failed=1, pending=50)) == 7500
    assert rules.rate_bp(OutcomeCounts(pending=2)) is None
    assert rules.rate_bp(OutcomeCounts()) is None
    assert OutcomeCounts(succeeded=3, failed=1, pending=50).completed == 4


@pytest.mark.parametrize(
    "succeeded,failed,expected",
    [(53, 42, 5579), (2, 1, 6667), (1, 2, 3333), (1, 7, 1250), (1, 15, 625), (1, 1999, 5), (1, 2001, 5)],
)
def test_rate_rounds_half_up_to_basis_points(succeeded: int, failed: int, expected: int) -> None:
    assert rules.rate_bp(OutcomeCounts(succeeded=succeeded, failed=failed)) == expected


def test_exactly_ten_points_below_baseline_is_degraded() -> None:
    baseline = OutcomeCounts(succeeded=90, failed=10)  # 90.0%
    assert rules.evaluate(OutcomeCounts(succeeded=80, failed=20), baseline) == "degraded"  # 80.0%: 10.0 points
    assert rules.evaluate(OutcomeCounts(succeeded=8001, failed=1999), OutcomeCounts(succeeded=9000, failed=1000)) == "within_range"  # 9.99 points


def test_drop_is_compared_exactly_not_on_rounded_rates() -> None:
    # 2/3 = 66.666...% vs baseline 76.666...%: exactly 10 points, though each rate rounds to a basis point.
    period = OutcomeCounts(succeeded=20, failed=10)
    baseline = OutcomeCounts(succeeded=230, failed=70)
    assert rules.evaluate(period, baseline) == "degraded"
    assert rules.delta_bp(period, baseline) == -1000


def test_an_improvement_is_within_range() -> None:
    assert rules.evaluate(OutcomeCounts(succeeded=50, failed=0), OutcomeCounts(succeeded=50, failed=50)) == "within_range"


def test_period_volume_guard_is_thirty_completed_attempts() -> None:
    baseline = OutcomeCounts(succeeded=100, failed=0)
    assert rules.evaluate(OutcomeCounts(succeeded=0, failed=29, pending=10), baseline) == "insufficient_volume"
    assert rules.evaluate(OutcomeCounts(succeeded=0, failed=30), baseline) == "degraded"


def test_baseline_volume_guard_is_one_hundred_completed_attempts() -> None:
    period = OutcomeCounts(succeeded=0, failed=30)
    assert rules.evaluate(period, OutcomeCounts(succeeded=99, failed=0, pending=5)) == "insufficient_volume"
    assert rules.evaluate(period, OutcomeCounts(succeeded=100, failed=0)) == "degraded"


def test_pending_only_and_empty_periods_draw_no_conclusion() -> None:
    baseline = OutcomeCounts(succeeded=500, failed=20)
    assert rules.evaluate(OutcomeCounts(pending=40), baseline) == "insufficient_volume"
    assert rules.evaluate(OutcomeCounts(), baseline) == "insufficient_volume"
    assert rules.delta_bp(OutcomeCounts(pending=40), baseline) is None


def test_baseline_is_the_thirty_chicago_days_before_the_period() -> None:
    assert rules.baseline_days(date(2026, 9, 29)) == (date(2026, 8, 30), date(2026, 9, 28))
    assert rules.baseline_days(date(2026, 10, 1)) == (date(2026, 9, 1), date(2026, 9, 30))


def test_format_rate() -> None:
    assert rules.format_rate(7204) == "72.0%"
    assert rules.format_rate(9079) == "90.8%"
    assert rules.format_rate(10000) == "100.0%"
    assert rules.format_rate(5) == "0.1%"


def test_failure_signal_labels_match_the_seeded_codes() -> None:
    assert FAILURE_CODE_LABELS == scenario.DECLINE_CODES
