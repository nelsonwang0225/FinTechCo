"""Payment Health rules: completed-attempt success rates and the degradation test.

Everything here is integer arithmetic. Rates are basis points (10000 = 100%) rounded half-up for display only; the
degradation decision compares the exact fractions, so a rate that rounds to the threshold never flips the result.
"""

from __future__ import annotations

from datetime import date, timedelta

BASELINE_DAYS = 30
DEGRADED_DROP_BP = 1000  # 10.0 percentage points below the channel's own baseline
MIN_COMPLETED_ATTEMPTS = 20  # in the period and in the baseline, per channel, before drawing a conclusion
LOW_VOLUME_DAY_ATTEMPTS = 10  # a trend day with fewer completed attempts is marked low volume
RECOVERY_WINDOW_SECONDS = 3600  # "recovered within 1 hour" of the payment's first attempt
UNRESOLVED_LIST_LIMIT = 10

BP_SCALE = 10_000


def rate_bp(succeeded: int, completed: int) -> int | None:
    """succeeded / completed in basis points, half-up; None when nothing completed (never a fabricated rate)."""
    if completed <= 0:
        return None
    return (2 * succeeded * BP_SCALE + completed) // (2 * completed)


def baseline_days(from_day: date) -> tuple[date, date]:
    """The BASELINE_DAYS Chicago dates immediately before the period."""
    return from_day - timedelta(days=BASELINE_DAYS), from_day - timedelta(days=1)


def assess(succeeded: int, completed: int, baseline_succeeded: int, baseline_completed: int) -> str:
    """'insufficient_volume', 'degraded' or 'not_degraded' for one channel.

    Degraded when baseline_rate - period_rate >= DEGRADED_DROP_BP / BP_SCALE, evaluated exactly:
    (bs/bc - ps/pc) * BP_SCALE >= DROP  <=>  (bs*pc - ps*bc) * BP_SCALE >= DROP * pc * bc.
    """
    if completed < MIN_COMPLETED_ATTEMPTS or baseline_completed < MIN_COMPLETED_ATTEMPTS:
        return "insufficient_volume"
    drop = (baseline_succeeded * completed - succeeded * baseline_completed) * BP_SCALE
    if drop >= DEGRADED_DROP_BP * completed * baseline_completed:
        return "degraded"
    return "not_degraded"
