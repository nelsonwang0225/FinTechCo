"""Payment Health rules: completed-attempt success rate, the degradation rule and per-payment recovery.

Pure functions over counts and timestamps; no SQL and no clock. Every comparison is integer arithmetic so the same
counts always give the same verdict. The thresholds are product constants echoed in the API response so the
definitions shown in the UI cannot drift from the rule that is applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from app.core.tz import parse_iso

MIN_COMPLETED_ATTEMPTS = 30  # period and baseline each need this many completed attempts before a channel is evaluated
DEGRADATION_POINTS = 5  # degraded when the success rate is at least this many percentage points below the baseline
LOW_VOLUME_DAY_ATTEMPTS = 10  # a trend day with fewer completed attempts is marked low volume
BASELINE_DAYS = 30  # the baseline is the same channel over this many Chicago days before the period
RECOVERY_WINDOW = timedelta(hours=1)

Assessment = Literal["degraded", "not_degraded", "insufficient_data", "no_completed_attempts"]
RecoveryState = Literal["recovered", "unresolved", "awaiting_outcome"]


@dataclass(frozen=True)
class AttemptCounts:
    succeeded: int = 0
    failed: int = 0
    pending: int = 0

    @property
    def completed(self) -> int:
        return self.succeeded + self.failed

    def __add__(self, other: AttemptCounts) -> AttemptCounts:
        return AttemptCounts(self.succeeded + other.succeeded, self.failed + other.failed, self.pending + other.pending)


def rate_bps(succeeded: int, completed: int) -> int | None:
    """Success rate in basis points (10000 = 100%), integer half-up; None when nothing completed."""
    if completed == 0:
        return None
    return (succeeded * 10000 * 2 + completed) // (completed * 2)


def change_bps(period: AttemptCounts, baseline: AttemptCounts) -> int | None:
    """Period rate minus baseline rate in basis points, from the rounded rates; None when either has no completed attempts."""
    p = rate_bps(period.succeeded, period.completed)
    b = rate_bps(baseline.succeeded, baseline.completed)
    if p is None or b is None:
        return None
    return p - b


def assess(period: AttemptCounts, baseline: AttemptCounts) -> Assessment:
    """Deterministic verdict for one channel (or all channels) against its own baseline."""
    if period.completed == 0:
        return "no_completed_attempts"
    if period.completed < MIN_COMPLETED_ATTEMPTS or baseline.completed < MIN_COMPLETED_ATTEMPTS:
        return "insufficient_data"
    # period_rate <= baseline_rate - points/100, cross-multiplied by 100 * c_p * c_b to stay in integers.
    cp, cb = period.completed, baseline.completed
    if 100 * period.succeeded * cb <= 100 * baseline.succeeded * cp - DEGRADATION_POINTS * cp * cb:
        return "degraded"
    return "not_degraded"


def recovery_state(succeeded_attempt_id: str | None, latest_outcome: str) -> RecoveryState:
    """Where an affected payment (one with a failed attempt) stands now."""
    if succeeded_attempt_id is not None:
        return "recovered"
    if latest_outcome == "pending":
        return "awaiting_outcome"
    return "unresolved"


def recovered_within_window(first_attempt_at: str, succeeded_at: str) -> bool:
    return parse_iso(succeeded_at) - parse_iso(first_attempt_at) <= RECOVERY_WINDOW
