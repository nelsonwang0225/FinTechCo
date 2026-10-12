"""Payment Health rules: completed-attempt success rates, the baseline window and the degradation verdict.

Everything here is integer arithmetic on counts. Rates are basis points (10000 = 100%) rounded half-up, and the
degraded rule is evaluated on the exact fractions by cross-multiplication, so no float ever decides a verdict.
The thresholds are returned by the API so the definitions shown in the product are the ones the rule used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.core.tz import parse_iso


@dataclass(frozen=True)
class Thresholds:
    degraded_drop_bp: int = 500  # 5.0 percentage points below baseline
    min_period_completed: int = 50
    min_baseline_completed: int = 200
    low_volume_day_completed: int = 10
    baseline_days: int = 30
    quick_recovery_seconds: int = 3600


THRESHOLDS = Thresholds()

ASSESSMENTS: tuple[str, ...] = ("degraded", "within_baseline", "insufficient_period_volume", "insufficient_baseline", "no_completed_attempts")


def rate_bp(succeeded: int, completed: int) -> int | None:
    """succeeded / completed in basis points, half-up; None when nothing completed (never a fabricated 0%)."""
    if completed <= 0:
        return None
    return (succeeded * 20000 + completed) // (2 * completed)


def change_bp(succeeded: int, completed: int, baseline_succeeded: int, baseline_completed: int) -> int | None:
    """Period rate minus baseline rate in basis points, from the exact fractions, rounded half away from zero."""
    if completed <= 0 or baseline_completed <= 0:
        return None
    numerator = 10000 * (succeeded * baseline_completed - baseline_succeeded * completed)
    denominator = completed * baseline_completed
    magnitude = (2 * abs(numerator) + denominator) // (2 * denominator)
    return magnitude if numerator >= 0 else -magnitude


def assess(succeeded: int, completed: int, baseline_succeeded: int, baseline_completed: int, t: Thresholds = THRESHOLDS) -> str:
    """The deterministic verdict for one channel. Low volume on either side never yields a conclusion."""
    if completed == 0:
        return "no_completed_attempts"
    if completed < t.min_period_completed:
        return "insufficient_period_volume"
    if baseline_completed < t.min_baseline_completed:
        return "insufficient_baseline"
    # rate <= baseline - drop  <=>  10000 * (s_b * c_p - s_p * c_b) >= drop * c_p * c_b
    shortfall = 10000 * (baseline_succeeded * completed - succeeded * baseline_completed)
    if shortfall >= t.degraded_drop_bp * completed * baseline_completed:
        return "degraded"
    return "within_baseline"


def is_low_volume_day(completed: int, t: Thresholds = THRESHOLDS) -> bool:
    """A day with some, but fewer than the threshold, completed attempts. A day with none is a gap, not low volume."""
    return 0 < completed < t.low_volume_day_completed


def baseline_days(from_day: date, t: Thresholds = THRESHOLDS) -> tuple[date, date]:
    """The inclusive Chicago dates of the baseline: the N days ending the day before the period starts."""
    return from_day - timedelta(days=t.baseline_days), from_day - timedelta(days=1)


def recovered_within(first_attempt_created_at: str, succeeded_at: str, seconds: int = THRESHOLDS.quick_recovery_seconds) -> bool:
    """True when the succeeding attempt completed within ``seconds`` of the payment's first attempt."""
    elapsed = parse_iso(succeeded_at) - parse_iso(first_attempt_created_at)
    return elapsed.total_seconds() <= seconds
