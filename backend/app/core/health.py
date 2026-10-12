"""Payment Health rules: completed-attempt success rate, each channel against its own baseline, and recovery timing.

Integer math only. A rate is basis points rounded half-up and is None when nothing completed; the degraded test
cross-multiplies the raw counts so no rounding can move a channel across the threshold. The thresholds are returned by
the API so the product shows the rule it applies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.core.tz import parse_iso

BASELINE_DAYS = 30
DEGRADED_DROP_BPS = 1000  # 10.0 percentage points below the baseline
MIN_PERIOD_COMPLETED = 30
MIN_BASELINE_COMPLETED = 100
LOW_VOLUME_DAY_COMPLETED = 10
RECOVERY_WINDOW_SECONDS = 3600


@dataclass(frozen=True)
class Counts:
    succeeded: int = 0
    failed: int = 0
    pending: int = 0

    @property
    def completed(self) -> int:
        return self.succeeded + self.failed

    @property
    def rate_bps(self) -> int | None:
        return rate_bps(self.succeeded, self.completed)


def rate_bps(succeeded: int, completed: int) -> int | None:
    """succeeded / completed in basis points, half-up; None when there is no completed attempt."""
    if completed == 0:
        return None
    return (succeeded * 20000 + completed) // (2 * completed)


def baseline_days(from_day: date) -> tuple[date, date]:
    """The BASELINE_DAYS Chicago dates immediately before the period."""
    return from_day - timedelta(days=BASELINE_DAYS), from_day - timedelta(days=1)


def is_degraded(period: Counts, baseline: Counts) -> bool:
    """period rate <= baseline rate - DEGRADED_DROP_BPS, exactly: 10000*(b_s*p_c - p_s*b_c) >= drop*b_c*p_c."""
    if period.completed == 0 or baseline.completed == 0:
        return False
    lhs = 10000 * (baseline.succeeded * period.completed - period.succeeded * baseline.completed)
    return lhs >= DEGRADED_DROP_BPS * baseline.completed * period.completed


def assess(period: Counts, baseline: Counts) -> str:
    if period.completed == 0:
        return "no_attempts"
    if period.completed < MIN_PERIOD_COMPLETED or baseline.completed < MIN_BASELINE_COMPLETED:
        return "insufficient_data"
    return "degraded" if is_degraded(period, baseline) else "normal"


def delta_bps(period: Counts, baseline: Counts) -> int | None:
    """Displayed difference between the two rounded rates; the assessment does not use it."""
    p, b = period.rate_bps, baseline.rate_bps
    if p is None or b is None:
        return None
    return p - b


def is_low_volume_day(day: Counts) -> bool:
    return day.completed < LOW_VOLUME_DAY_COMPLETED


def recovered_within(first_attempt_at: str, succeeded_at: str, seconds: int = RECOVERY_WINDOW_SECONDS) -> bool:
    """The succeeding attempt completed within ``seconds`` of the payment's first attempt."""
    return (parse_iso(succeeded_at) - parse_iso(first_attempt_at)).total_seconds() <= seconds
