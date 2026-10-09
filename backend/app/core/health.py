"""Payment Health rules: completed-attempt success rates, the baseline comparison and payment recovery.

Deterministic integer arithmetic only. Rates are basis points (1/100 of a percent) rounded half-up from the counts,
and every rule below is echoed to the frontend as ``rules`` so the product states exactly what was applied.

- Success rate: succeeded / (succeeded + failed) over attempts created in the period. Pending attempts are counted
  but never enter the denominator; with no completed attempts there is no rate.
- Baseline: the same scope over the BASELINE_DAYS Chicago days immediately before the period.
- A channel is evaluated only with at least MIN_PERIOD_COMPLETED completed attempts in the period and
  MIN_BASELINE_COMPLETED in the baseline; it is degraded when its rate is DEGRADED_DROP_BP or more below its baseline.
- Recovery is per payment, not per attempt: a payment with a failed attempt is affected; it is recovered once any
  attempt succeeds, in progress while its latest attempt is pending, and unresolved when its latest attempt failed.
"""

from __future__ import annotations

from dataclasses import dataclass

BASELINE_DAYS = 30
DEGRADED_DROP_BP = 1000
MIN_PERIOD_COMPLETED = 50
MIN_BASELINE_COMPLETED = 200
LOW_VOLUME_DAY_COMPLETED = 20
QUICK_RECOVERY_SECONDS = 3600
UNRESOLVED_LIST_SIZE = 10


@dataclass(frozen=True)
class OutcomeCounts:
    succeeded: int = 0
    failed: int = 0
    pending: int = 0

    @property
    def completed(self) -> int:
        return self.succeeded + self.failed

    @property
    def total(self) -> int:
        return self.completed + self.pending

    @property
    def rate_bp(self) -> int | None:
        return success_rate_bp(self.succeeded, self.failed)

    def __add__(self, other: OutcomeCounts) -> OutcomeCounts:
        return OutcomeCounts(self.succeeded + other.succeeded, self.failed + other.failed, self.pending + other.pending)


def success_rate_bp(succeeded: int, failed: int) -> int | None:
    """succeeded / (succeeded + failed) in basis points, half-up; None when nothing completed."""
    completed = succeeded + failed
    if completed == 0:
        return None
    return (succeeded * 20000 + completed) // (2 * completed)


def change_bp(period: OutcomeCounts, baseline: OutcomeCounts) -> int | None:
    if period.rate_bp is None or baseline.rate_bp is None:
        return None
    return period.rate_bp - baseline.rate_bp


def assess(period: OutcomeCounts, baseline: OutcomeCounts) -> str:
    """degraded | healthy | insufficient_volume | no_attempts for one channel."""
    if period.total == 0:
        return "no_attempts"
    if period.completed < MIN_PERIOD_COMPLETED or baseline.completed < MIN_BASELINE_COMPLETED:
        return "insufficient_volume"
    change = change_bp(period, baseline)
    assert change is not None
    return "degraded" if -change >= DEGRADED_DROP_BP else "healthy"


def attention_state(assessments: list[str], completed_in_period: int) -> str:
    """The page-level conclusion across every channel."""
    if "degraded" in assessments:
        return "degraded"
    if "healthy" in assessments:
        return "healthy"
    if completed_in_period == 0:
        return "no_completed_attempts"
    return "insufficient_volume"


def low_volume_day(counts: OutcomeCounts) -> bool:
    """A day with some, but fewer than LOW_VOLUME_DAY_COMPLETED, completed attempts. A day with none is a gap."""
    return 0 < counts.completed < LOW_VOLUME_DAY_COMPLETED
