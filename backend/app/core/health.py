"""Payment Health rules: completed-attempt success against a per-channel baseline, and recovery per payment.

Pure functions over rows from app.db.queries.payment_health; nothing here reads the database or a clock.

- A completed attempt has outcome succeeded or failed. Pending attempts are counted but never enter a rate.
- Success rate = succeeded / completed, in integer basis points rounded half-up; None when nothing completed.
- Baseline = the same channel over the BASELINE_DAYS Chicago days before the period.
- A channel is degraded when the period has at least MIN_PERIOD_COMPLETED completed attempts, the baseline at least
  MIN_BASELINE_COMPLETED, and the period rate is at least DEGRADED_DROP_BP below the baseline rate.
- An affected payment has at least one failed attempt. It is recovered when it has a succeeded attempt (at most one
  exists and nothing follows it), unresolved when its status is failed, and in progress when its latest attempt is
  pending. Its amount counts once, whatever its number of attempts.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.core.tz import chicago_day, parse_iso

BASELINE_DAYS = 30
DEGRADED_DROP_BP = 1000  # 10.0 percentage points
MIN_PERIOD_COMPLETED = 50
MIN_BASELINE_COMPLETED = 100
LOW_VOLUME_DAY_COMPLETED = 10
QUICK_RECOVERY_SECONDS = 3600

RECOVERED_STATUSES = frozenset({"succeeded", "partially_refunded", "refunded"})


def rate_bp(succeeded: int, completed: int) -> int | None:
    """succeeded / completed in basis points, integer half-up."""
    if completed == 0:
        return None
    return (2 * succeeded * 10000 + completed) // (2 * completed)


@dataclass
class Counts:
    succeeded: int = 0
    failed: int = 0
    pending: int = 0

    @property
    def completed(self) -> int:
        return self.succeeded + self.failed

    @property
    def rate_bp(self) -> int | None:
        return rate_bp(self.succeeded, self.completed)

    def add(self, outcome: str) -> None:
        if outcome == "succeeded":
            self.succeeded += 1
        elif outcome == "failed":
            self.failed += 1
        elif outcome == "pending":
            self.pending += 1
        else:
            raise ValueError(f"unknown attempt outcome {outcome!r}")


def count_attempts(rows: Iterable[Mapping[str, Any]], channel: str | None = None) -> Counts:
    counts = Counts()
    for row in rows:
        if channel is None or row["channel"] == channel:
            counts.add(row["outcome"])
    return counts


def change_bp(period: Counts, baseline: Counts) -> int | None:
    if period.rate_bp is None or baseline.rate_bp is None:
        return None
    return period.rate_bp - baseline.rate_bp


def assess(period: Counts, baseline: Counts) -> str:
    """One of degraded, no_significant_degradation, insufficient_volume, no_completed_attempts."""
    if period.completed == 0:
        return "no_completed_attempts"
    if period.completed < MIN_PERIOD_COMPLETED or baseline.completed < MIN_BASELINE_COMPLETED:
        return "insufficient_volume"
    change = change_bp(period, baseline)
    assert change is not None
    return "degraded" if -change >= DEGRADED_DROP_BP else "no_significant_degradation"


def attention_state(assessments: Iterable[str]) -> str:
    """The page-level conclusion over every channel's assessment."""
    found = set(assessments)
    if "degraded" in found:
        return "degraded"
    if "no_significant_degradation" in found:
        return "no_significant_degradation"
    if "insufficient_volume" in found:
        return "insufficient_data"
    return "no_completed_attempts"


def baseline_days(from_day: date) -> tuple[date, date]:
    """The BASELINE_DAYS Chicago dates ending the day before the period starts."""
    return from_day - timedelta(days=BASELINE_DAYS), from_day - timedelta(days=1)


def days_with_completed(rows: Iterable[Mapping[str, Any]], channel: str | None = None) -> int:
    return len({chicago_day(r["created_at"]) for r in rows if r["outcome"] != "pending" and (channel is None or r["channel"] == channel)})


@dataclass(frozen=True)
class DayPoint:
    day: date
    counts: Counts
    low_volume: bool


def daily_trend(rows: Iterable[Mapping[str, Any]], days: list[date], channel: str | None = None) -> list[DayPoint]:
    """One point per Chicago day. A day with no completed attempt has no rate (a gap, not zero); a day with fewer than
    LOW_VOLUME_DAY_COMPLETED completed attempts is marked low volume."""
    by_day = {day: Counts() for day in days}
    for row in rows:
        if channel is not None and row["channel"] != channel:
            continue
        day = chicago_day(row["created_at"])
        if day in by_day:
            by_day[day].add(row["outcome"])
    return [DayPoint(day=day, counts=c, low_volume=0 < c.completed < LOW_VOLUME_DAY_COMPLETED) for day, c in by_day.items()]


def signal_counts(rows: Iterable[Mapping[str, Any]], channel: str | None = None) -> list[tuple[str, int]]:
    """Failed attempts per recorded failure code, most frequent first (ties by code)."""
    counts: dict[str, int] = {}
    for row in rows:
        if row["outcome"] == "failed" and (channel is None or row["channel"] == channel):
            counts[row["failure_code"]] = counts.get(row["failure_code"], 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


@dataclass
class Group:
    payments: int = 0
    amount_cents: int = 0

    def add(self, amount_cents: int) -> None:
        self.payments += 1
        self.amount_cents += amount_cents


@dataclass
class Recovery:
    affected: Group = field(default_factory=Group)
    recovered: Group = field(default_factory=Group)
    recovered_within_hour: Group = field(default_factory=Group)
    unresolved: Group = field(default_factory=Group)
    in_progress: Group = field(default_factory=Group)


def recovered_within_hour(first_attempt_at: str, succeeded_at: str) -> bool:
    return (parse_iso(succeeded_at) - parse_iso(first_attempt_at)).total_seconds() <= QUICK_RECOVERY_SECONDS


def recovery(rows: Iterable[Mapping[str, Any]]) -> Recovery:
    """Group affected payments (one row each) by how they ended."""
    result = Recovery()
    for row in rows:
        amount = int(row["amount_cents"])
        result.affected.add(amount)
        status = row["status"]
        if status in RECOVERED_STATUSES:
            result.recovered.add(amount)
            if recovered_within_hour(row["first_attempt_at"], row["succeeded_at"]):
                result.recovered_within_hour.add(amount)
        elif status == "failed":
            result.unresolved.add(amount)
        elif status == "pending":
            result.in_progress.add(amount)
        else:
            raise ValueError(f"unknown payment status {status!r}")
    return result
