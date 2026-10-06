"""Payment Health: the deterministic degradation rule. Pure functions, no SQL.

Success rate is measured on completed attempts only: succeeded / (succeeded + failed). Pending attempts are counted
and reported but never enter the denominator. A channel is compared with its own baseline, the same channel over the
30 America/Chicago days immediately before the period. It is evaluated only when both sides have enough completed
attempts, and it is degraded when its rate is at least DEGRADED_DROP_BP below the baseline. The comparison is exact
(rational arithmetic); rates on the wire are basis points rounded half-up for display.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from typing import Literal

BASELINE_DAYS = 30
MIN_PERIOD_COMPLETED = 30
MIN_BASELINE_COMPLETED = 100
DEGRADED_DROP_BP = 1000  # 10.0 percentage points

Evaluation = Literal["degraded", "within_range", "insufficient_volume"]


@dataclass(frozen=True)
class OutcomeCounts:
    succeeded: int = 0
    failed: int = 0
    pending: int = 0

    @property
    def completed(self) -> int:
        return self.succeeded + self.failed

    @property
    def rate(self) -> Fraction | None:
        return Fraction(self.succeeded, self.completed) if self.completed else None

    def __add__(self, other: OutcomeCounts) -> OutcomeCounts:
        return OutcomeCounts(self.succeeded + other.succeeded, self.failed + other.failed, self.pending + other.pending)


def rate_bp(counts: OutcomeCounts) -> int | None:
    """Success rate in basis points, rounded half-up; None when there are no completed attempts."""
    if counts.completed == 0:
        return None
    return (counts.succeeded * 20000 + counts.completed) // (counts.completed * 2)


def delta_bp(period: OutcomeCounts, baseline: OutcomeCounts) -> int | None:
    """Period rate minus baseline rate in basis points, rounded half-up (negative is a drop)."""
    if period.rate is None or baseline.rate is None:
        return None
    diff = (period.rate - baseline.rate) * 10000
    return (diff.numerator * 2 + diff.denominator) // (diff.denominator * 2)


def baseline_days(from_day: date) -> tuple[date, date]:
    """The inclusive Chicago date range of the baseline: the BASELINE_DAYS days before the period starts."""
    return from_day - timedelta(days=BASELINE_DAYS), from_day - timedelta(days=1)


def format_rate(bp: int) -> str:
    """Basis points as a percentage with one decimal, rounded half-up: 7204 -> '72.0%'."""
    tenths = (bp + 5) // 10
    return f"{tenths // 10}.{tenths % 10}%"


def evaluate(period: OutcomeCounts, baseline: OutcomeCounts) -> Evaluation:
    if period.completed < MIN_PERIOD_COMPLETED or baseline.completed < MIN_BASELINE_COMPLETED:
        return "insufficient_volume"
    assert period.rate is not None and baseline.rate is not None
    drop = (baseline.rate - period.rate) * 10000
    return "degraded" if drop >= DEGRADED_DROP_BP else "within_range"
