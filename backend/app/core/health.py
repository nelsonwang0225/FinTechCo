"""Payment Health rules: completed-attempt success rates, the per-channel degradation verdict and per-payment recovery.

Everything here is integer arithmetic over counts the queries return. Rates are basis points (10000 = 100%), rounded
half-up, and ``None`` when there are no completed attempts, so the page never shows a fabricated rate. The thresholds
are fixed constants, returned to the client in a ``rules`` block so the product can state them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.core.tz import parse_iso

BASELINE_DAYS = 30
MIN_PERIOD_COMPLETED = 30
MIN_BASELINE_COMPLETED = 100
DEGRADED_DROP_BPS = 500
LOW_VOLUME_DAY_COMPLETED = 10
QUICK_RECOVERY = timedelta(hours=1)

VERDICT_LABELS: dict[str, str] = {
    "degraded": "Degraded",
    "ok": "No significant degradation",
    "insufficient_data": "Not enough data",
    "no_data": "No completed attempts",
}


@dataclass(frozen=True)
class OutcomeCounts:
    succeeded: int = 0
    failed: int = 0
    pending: int = 0

    @property
    def completed(self) -> int:
        return self.succeeded + self.failed

    def __add__(self, other: OutcomeCounts) -> OutcomeCounts:
        return OutcomeCounts(self.succeeded + other.succeeded, self.failed + other.failed, self.pending + other.pending)


def rate_bps(numerator: int, denominator: int) -> int | None:
    """numerator / denominator in basis points, integer half-up; None for an empty denominator."""
    if denominator <= 0:
        return None
    return (numerator * 10000 * 2 + denominator) // (denominator * 2)


def success_rate_bps(counts: OutcomeCounts) -> int | None:
    return rate_bps(counts.succeeded, counts.completed)


def verdict(period: OutcomeCounts, baseline: OutcomeCounts) -> str:
    """degraded | ok | insufficient_data | no_data, from the fixed thresholds above."""
    if period.completed == 0:
        return "no_data"
    if period.completed < MIN_PERIOD_COMPLETED or baseline.completed < MIN_BASELINE_COMPLETED:
        return "insufficient_data"
    current = success_rate_bps(period)
    reference = success_rate_bps(baseline)
    assert current is not None and reference is not None
    return "degraded" if reference - current >= DEGRADED_DROP_BPS else "ok"


def recovered_quickly(first_attempt_at: str, succeeded_at: str | None) -> bool:
    """True when the succeeding attempt completed within one hour of the payment's first attempt."""
    if succeeded_at is None:
        return False
    return parse_iso(succeeded_at) - parse_iso(first_attempt_at) <= QUICK_RECOVERY
