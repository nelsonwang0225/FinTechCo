"""Payment Health: the degradation rule, its thresholds and the recovery states, in one place.

Every verdict a merchant reads on the Payment Health page comes from this module and nowhere else. The numbers are
deliberately plain so the product can quote them:

- A rate is completed-attempt success: succeeded / (succeeded + failed), in integer basis points rounded half-up.
  Pending attempts are excluded (the schema knows no canceled outcome).
- The baseline for a period is the same channel over the ``BASELINE_DAYS`` Chicago days before the period starts.
- A channel is evaluated only with ``MIN_PERIOD_COMPLETED`` completed attempts in the period and
  ``MIN_BASELINE_COMPLETED`` in the baseline. Below the baseline minimum the verdict is ``no_baseline`` when the
  merchant's recorded history starts inside the baseline window (there is nothing to compare against yet) and
  ``insufficient_volume`` otherwise.
- With enough volume the channel is ``degraded`` when its rate is at least ``DEGRADED_DROP_BP`` below the baseline,
  else ``normal``. Normal means no significant degradation was detected; it never means every payment succeeded.
- A trend day with fewer than ``LOW_VOLUME_DAY_COMPLETED`` completed attempts is marked low volume, and the worst day
  quoted as evidence is picked among days with at least that many (falling back to any day with a completed attempt).
- Recovery is counted per payment, never per attempt. An affected payment has at least one failed attempt. It is
  recovered when a succeeded attempt exists: within the window when that attempt completed no later than
  ``RECOVERY_WINDOW`` after the payment's first attempt was created, later otherwise. With no success it is
  ``attempt_pending`` when its latest attempt is pending and ``unresolved`` otherwise, which is exactly the Payments
  list's ``failed`` status.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.core.tz import parse_iso

BASELINE_DAYS = 30
MIN_PERIOD_COMPLETED = 30
MIN_BASELINE_COMPLETED = 100
DEGRADED_DROP_BP = 1000
LOW_VOLUME_DAY_COMPLETED = 10
RECOVERY_WINDOW = timedelta(hours=1)

ChannelStatus = Literal["degraded", "normal", "insufficient_volume", "no_baseline"]
RecoveryState = Literal["recovered_within_window", "recovered_later", "attempt_pending", "unresolved"]


def rate_bp(numerator: int, denominator: int) -> int | None:
    """numerator / denominator in basis points, rounded half-up in integer arithmetic; None without a denominator."""
    if denominator <= 0:
        return None
    return (2 * 10000 * numerator + denominator) // (2 * denominator)


@dataclass(frozen=True)
class Outcomes:
    """Attempt outcome counts for one scope. Completed = succeeded + failed; pending attempts never enter a rate."""

    succeeded: int = 0
    failed: int = 0
    pending: int = 0

    @property
    def completed(self) -> int:
        return self.succeeded + self.failed

    @property
    def success_rate_bp(self) -> int | None:
        return rate_bp(self.succeeded, self.completed)

    @property
    def failed_share_bp(self) -> int | None:
        return rate_bp(self.failed, self.completed)


@dataclass(frozen=True)
class DayOutcomes(Outcomes):
    day: date = date.min

    @property
    def low_volume(self) -> bool:
        return self.completed < LOW_VOLUME_DAY_COMPLETED


def baseline_window(period_from: date) -> tuple[date, date]:
    """Inclusive Chicago dates of the baseline: the BASELINE_DAYS days ending the day before the period starts."""
    return period_from - timedelta(days=BASELINE_DAYS), period_from - timedelta(days=1)


def evaluate(period: Outcomes, baseline: Outcomes, *, baseline_from: date, history_starts: date | None) -> ChannelStatus:
    """The verdict for one channel. `history_starts` is the Chicago date of the merchant's first recorded attempt."""
    if period.completed < MIN_PERIOD_COMPLETED:
        return "insufficient_volume"
    if baseline.completed < MIN_BASELINE_COMPLETED:
        if history_starts is None or history_starts > baseline_from:
            return "no_baseline"
        return "insufficient_volume"
    period_rate, baseline_rate = period.success_rate_bp, baseline.success_rate_bp
    assert period_rate is not None and baseline_rate is not None
    return "degraded" if baseline_rate - period_rate >= DEGRADED_DROP_BP else "normal"


def drop_bp(period: Outcomes, baseline: Outcomes) -> int | None:
    """Baseline rate minus period rate in basis points (positive = worse than baseline); None without both rates."""
    period_rate, baseline_rate = period.success_rate_bp, baseline.success_rate_bp
    if period_rate is None or baseline_rate is None:
        return None
    return baseline_rate - period_rate


def worst_day(days: Sequence[DayOutcomes]) -> DayOutcomes | None:
    """The lowest-rate day among days with enough volume, else among days with any completed attempt; None if none."""
    candidates = [d for d in days if not d.low_volume] or [d for d in days if d.completed > 0]
    if not candidates:
        return None
    return min(candidates, key=lambda d: (d.success_rate_bp or 0, d.day))


def recovery_state(*, succeeded_at: str | None, latest_outcome: str, first_attempt_at: str) -> RecoveryState:
    """Classify one affected payment from its attempt chain."""
    if succeeded_at is not None:
        within = parse_iso(succeeded_at) - parse_iso(first_attempt_at) <= RECOVERY_WINDOW
        return "recovered_within_window" if within else "recovered_later"
    if latest_outcome == "pending":
        return "attempt_pending"
    return "unresolved"


# --------------------------------------------------------------------------- scope verdict and attention copy
#
# Everything below is pure text and arithmetic over the verdicts above, so the API handler only assembles rows
# and tests can pin the exact wording.

CHANNELS: tuple[str, ...] = ("website", "mobile_app", "in_store")
ALL_CHANNELS_LABEL = "All channels"


def aggregate_status(statuses: Sequence[ChannelStatus]) -> ChannelStatus:
    """The all-channels verdict is the worst of the per-channel verdicts, never a rule run over the pooled counts."""
    if "degraded" in statuses:
        return "degraded"
    if "normal" in statuses:
        return "normal"
    if "no_baseline" in statuses:
        return "no_baseline"
    return "insufficient_volume"


def format_rate_bp(bp: int) -> str:
    """A rate in basis points as a percentage with one decimal, half-up: 7204 -> '72.0%', 5579 -> '55.8%'."""
    whole, tenth = divmod((bp + 5) // 10, 10)
    return f"{whole}.{tenth}%"


def format_points_bp(bp: int) -> str:
    """A difference in basis points as percentage points, magnitude only: 1875 -> '18.8 pts'."""
    whole, tenth = divmod((abs(bp) + 5) // 10, 10)
    return f"{whole}.{tenth} pts"


def day_label(day: date, *, with_year: bool = False) -> str:
    """'Oct 1' or 'Oct 1, 2026', the same spelling the period labels use."""
    month = day.strftime("%b")
    return f"{month} {day.day}, {day.year}" if with_year else f"{month} {day.day}"


def date_range_label(from_day: date, to_day: date) -> str:
    """'Aug 7 – Sep 5, 2026', the same spelling as a period's range label."""
    if from_day == to_day:
        return day_label(from_day, with_year=True)
    left = day_label(from_day, with_year=from_day.year != to_day.year)
    return f"{left} – {day_label(to_day, with_year=True)}"


@dataclass(frozen=True)
class ChannelVerdict:
    """One evaluated channel, as the attention copy needs it."""

    channel: str
    label: str
    status: ChannelStatus
    period: Outcomes
    baseline: Outcomes
    worst_day: DayOutcomes | None = None


def degraded_headline(labels: Sequence[str]) -> str:
    return f"Attention needed: {' and '.join(labels)} payment performance degraded"


def degraded_detail(verdicts: Sequence[ChannelVerdict]) -> str:
    """One sentence per degraded channel, with its worst day as evidence when there is one."""
    sentences: list[str] = []
    for v in verdicts:
        if v.status != "degraded":
            continue
        period_rate, baseline_rate = v.period.success_rate_bp, v.baseline.success_rate_bp
        assert period_rate is not None and baseline_rate is not None
        sentences.append(
            f"{v.label}: {format_rate_bp(period_rate)} of completed attempts succeeded vs {format_rate_bp(baseline_rate)} in the baseline "
            f"({format_points_bp(baseline_rate - period_rate)} lower)."
        )
        if v.worst_day is not None and v.worst_day.success_rate_bp is not None:
            sentences.append(f"Worst day {day_label(v.worst_day.day)}: {format_rate_bp(v.worst_day.success_rate_bp)} of {v.worst_day.completed} completed attempts.")
    return " ".join(sentences)


NORMAL_HEADLINE = "No significant degradation detected for the selected scope"


def normal_detail(verdicts: Sequence[ChannelVerdict]) -> str:
    """Every channel with a verdict of normal, period rate vs baseline rate."""
    parts: list[str] = []
    for v in verdicts:
        if v.status != "normal":
            continue
        period_rate, baseline_rate = v.period.success_rate_bp, v.baseline.success_rate_bp
        assert period_rate is not None and baseline_rate is not None
        parts.append(f"{v.label} {format_rate_bp(period_rate)} vs {format_rate_bp(baseline_rate)}")
    return (
        f"Completed-attempt success is within {format_points_bp(DEGRADED_DROP_BP)} of the baseline for every channel with enough volume: "
        f"{', '.join(parts)}. Individual payments can still fail; the unresolved list shows which."
    )


INSUFFICIENT_VOLUME_HEADLINE = "Insufficient volume to evaluate payment health"


def insufficient_volume_detail(period: Outcomes, baseline: Outcomes) -> str:
    return (
        f"{period.completed} completed attempts in the period ({MIN_PERIOD_COMPLETED} needed) and {baseline.completed} in the baseline "
        f"({MIN_BASELINE_COMPLETED} needed). Counts are shown without a verdict."
    )


def no_baseline_headline(history_starts: date | None) -> str:
    if history_starts is None:
        return "No baseline yet: no recorded payment attempts"
    return f"No baseline yet: payment history starts {day_label(history_starts, with_year=True)}"


def no_baseline_detail(baseline_from: date, baseline_to: date, history_starts: date | None, baseline: Outcomes) -> str:
    window = date_range_label(baseline_from, baseline_to)
    if history_starts is None:
        return f"The baseline would be {window}, but this business has no recorded payment attempts yet. Period figures are shown without a verdict."
    return (
        f"The baseline would be {window}, but recorded history begins {day_label(history_starts, with_year=True)}, leaving {baseline.completed} completed "
        f"attempts to compare against ({MIN_BASELINE_COMPLETED} needed). Period figures are shown without a verdict."
    )


def attention_text(
    status: ChannelStatus,
    verdicts: Sequence[ChannelVerdict],
    *,
    scope_period: Outcomes,
    scope_baseline: Outcomes,
    baseline_from: date,
    baseline_to: date,
    history_starts: date | None,
) -> tuple[str, str]:
    """(headline, detail) for the selected scope. `verdicts` are the channels the scope evaluates."""
    if status == "degraded":
        return degraded_headline([v.label for v in verdicts if v.status == "degraded"]), degraded_detail(verdicts)
    if status == "normal":
        return NORMAL_HEADLINE, normal_detail(verdicts)
    if status == "no_baseline":
        return no_baseline_headline(history_starts), no_baseline_detail(baseline_from, baseline_to, history_starts, scope_baseline)
    return INSUFFICIENT_VOLUME_HEADLINE, insufficient_volume_detail(scope_period, scope_baseline)
