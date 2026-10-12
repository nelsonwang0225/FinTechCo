"""Payment Health rules: integer rates, the degraded verdict at its boundaries, the baseline window and quick recovery."""

from __future__ import annotations

from datetime import date

import pytest

from app.core import health
from app.core.labels import FAILURE_CODE_LABELS, HEALTH_ASSESSMENT_LABELS
from app.seed import scenario


def test_rate_is_basis_points_half_up_and_none_without_completed_attempts() -> None:
    assert health.rate_bp(0, 0) is None
    assert health.rate_bp(0, 5) == 0
    assert health.rate_bp(5, 5) == 10000
    assert health.rate_bp(2, 3) == 6667  # 6666.67
    assert health.rate_bp(1, 8) == 1250
    assert health.rate_bp(1, 16) == 625  # 625.0 exactly
    assert health.rate_bp(1, 32) == 313  # 312.5 rounds half-up


def test_change_is_exact_and_signed() -> None:
    assert health.change_bp(80, 100, 90, 100) == -1000
    assert health.change_bp(90, 100, 80, 100) == 1000
    assert health.change_bp(1, 3, 1, 3) == 0
    assert health.change_bp(0, 0, 9, 10) is None
    assert health.change_bp(9, 10, 0, 0) is None


@pytest.mark.parametrize(
    "s, c, sb, cb, expected",
    [
        (85, 100, 900, 1000, "degraded"),  # exactly 5.0 points below
        (851, 1000, 900, 1000, "within_baseline"),  # 4.9 points below
        (40, 100, 900, 1000, "degraded"),
        (100, 100, 900, 1000, "within_baseline"),  # improvements are never degraded
        (0, 49, 900, 1000, "insufficient_period_volume"),
        (0, 50, 900, 1000, "degraded"),
        (10, 50, 199, 199, "insufficient_baseline"),
        (10, 50, 200, 200, "degraded"),
        (0, 0, 900, 1000, "no_completed_attempts"),
        (45, 50, 0, 0, "insufficient_baseline"),
    ],
)
def test_assess_boundaries(s: int, c: int, sb: int, cb: int, expected: str) -> None:
    assert health.assess(s, c, sb, cb) == expected
    assert expected in health.ASSESSMENTS and expected in HEALTH_ASSESSMENT_LABELS


def test_assess_uses_exact_fractions_not_rounded_rates() -> None:
    # 2/3 = 66.67% vs a 71.67% baseline is exactly 5 points; rounding either rate first could flip the verdict.
    assert health.assess(200, 300, 4300, 6000) == "degraded"
    assert health.assess(201, 300, 4300, 6000) == "within_baseline"


def test_low_volume_days_and_gaps() -> None:
    assert not health.is_low_volume_day(0)
    assert health.is_low_volume_day(1)
    assert health.is_low_volume_day(9)
    assert not health.is_low_volume_day(10)


def test_baseline_is_the_thirty_days_before_the_period() -> None:
    assert health.baseline_days(date(2026, 10, 1)) == (date(2026, 9, 1), date(2026, 9, 30))
    assert health.baseline_days(date(2026, 9, 29)) == (date(2026, 8, 30), date(2026, 9, 28))


def test_recovered_within_an_hour_is_inclusive() -> None:
    assert health.recovered_within("2026-10-01T20:00:00Z", "2026-10-01T21:00:00Z")
    assert not health.recovered_within("2026-10-01T20:00:00Z", "2026-10-01T21:00:01Z")
    assert health.recovered_within("2026-10-02T04:50:00Z", "2026-10-02T05:10:00Z")  # across a Chicago midnight


def test_failure_code_labels_match_the_seeded_codes() -> None:
    assert FAILURE_CODE_LABELS == scenario.DECLINE_CODES
