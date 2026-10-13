"""Payment Health rules: completed-attempt success rate, the per-channel baseline and the degraded verdict.

Pure functions over counts; no SQL and no clock. Rates are integer basis points (1 bp = 0.01 percentage point),
rounded half-up, so the summary, the channel table and the chart all show the same number.

- Success rate = succeeded / (succeeded + failed). Pending attempts are not completed and are counted separately.
- Baseline = the same channel over the BASELINE_DAYS Chicago days before the period's first day.
- A channel is evaluated only with at least MIN_PERIOD_COMPLETED completed attempts in the period and
  MIN_BASELINE_COMPLETED in the baseline; it is degraded when its rate is DEGRADED_DROP_BP or more below the baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from app.core.periods import Period
from app.core.tz import chicago_range

BASELINE_DAYS = 30
DEGRADED_DROP_BP = 1000  # 10 percentage points
MIN_PERIOD_COMPLETED = 50
MIN_BASELINE_COMPLETED = 200
LOW_VOLUME_DAY_COMPLETED = 10
RECOVERY_WINDOW_SECONDS = 3600

Verdict = Literal["degraded", "not_degraded", "insufficient_data", "no_data"]


@dataclass(frozen=True)
class Counts:
    succeeded: int = 0
    failed: int = 0
    pending: int = 0

    @property
    def completed(self) -> int:
        return self.succeeded + self.failed

    def __add__(self, other: Counts) -> Counts:
        return Counts(self.succeeded + other.succeeded, self.failed + other.failed, self.pending + other.pending)


def rate_bp(counts: Counts) -> int | None:
    """Success rate in basis points, half-up; None when nothing completed."""
    if counts.completed == 0:
        return None
    return (2 * counts.succeeded * 10_000 + counts.completed) // (2 * counts.completed)


def change_bp(period: Counts, baseline: Counts) -> int | None:
    """Period rate minus baseline rate, in basis points; negative is worse."""
    current, base = rate_bp(period), rate_bp(baseline)
    if current is None or base is None:
        return None
    return current - base


def evaluate(period: Counts, baseline: Counts) -> Verdict:
    if period.completed == 0:
        return "no_data"
    if period.completed < MIN_PERIOD_COMPLETED or baseline.completed < MIN_BASELINE_COMPLETED:
        return "insufficient_data"
    change = change_bp(period, baseline)
    assert change is not None
    return "degraded" if -change >= DEGRADED_DROP_BP else "not_degraded"


def baseline_period(period: Period) -> Period:
    """The BASELINE_DAYS Chicago calendar days immediately before the period's first day."""
    to_day = period.from_day - timedelta(days=1)
    from_day = period.from_day - timedelta(days=BASELINE_DAYS)
    start, end = chicago_range(from_day, to_day)
    return Period(preset="custom", from_day=from_day, to_day=to_day, start=start, end=end)
