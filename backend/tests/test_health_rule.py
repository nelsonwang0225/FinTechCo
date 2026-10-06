"""The Payment Health rule on synthetic inputs: rates, verdicts, worst day, recovery states and the attention copy."""

from __future__ import annotations

from datetime import date

import pytest

from app.core import health, periods
from app.core.health import ChannelVerdict, DayOutcomes, Outcomes
from app.core.tz import chicago_local, to_iso

HISTORY = date(2026, 6, 1)  # long before any baseline in these cases
BASELINE_FROM = date(2026, 9, 1)


@pytest.mark.parametrize(
    "numerator,denominator,expected",
    [(0, 0, None), (5, 0, None), (0, 7, 0), (7, 7, 10000), (1, 3, 3333), (2, 3, 6667), (1, 8, 1250), (1, 16, 625), (3, 16, 1875), (53, 95, 5579), (1, 20000, 1)],
)
def test_rate_bp_is_half_up_integer_arithmetic(numerator: int, denominator: int, expected: int | None) -> None:
    assert health.rate_bp(numerator, denominator) == expected


def test_outcomes_exclude_pending_from_every_rate() -> None:
    o = Outcomes(succeeded=3, failed=1, pending=6)
    assert o.completed == 4 and o.success_rate_bp == 7500 and o.failed_share_bp == 2500
    assert Outcomes(pending=2).completed == 0 and Outcomes(pending=2).success_rate_bp is None


def test_baseline_window_is_the_30_days_before_the_period() -> None:
    assert health.baseline_window(date(2026, 10, 1)) == (date(2026, 9, 1), date(2026, 9, 30))
    assert health.baseline_window(date(2026, 9, 29)) == (date(2026, 8, 30), date(2026, 9, 28))
    assert health.baseline_window(date(2026, 9, 6)) == (date(2026, 8, 7), date(2026, 9, 5))


def verdict(period_s: int, period_f: int, base_s: int, base_f: int, *, history: date | None = HISTORY) -> health.ChannelStatus:
    return health.evaluate(Outcomes(period_s, period_f), Outcomes(base_s, base_f), baseline_from=BASELINE_FROM, history_starts=history)


def test_evaluate_needs_30_completed_in_the_period() -> None:
    assert verdict(20, 9, 900, 100) == "insufficient_volume"
    assert verdict(20, 9, 900, 100, history=None) == "insufficient_volume", "the period minimum is checked first"
    assert verdict(21, 9, 900, 100) == "degraded", "30 completed is evaluated, and 70.0% vs 90.0% is a 20.0 pt drop"
    assert verdict(27, 3, 900, 100) == "normal"


def test_evaluate_needs_100_completed_in_the_baseline() -> None:
    assert verdict(30, 0, 90, 9) == "insufficient_volume"
    assert verdict(30, 0, 90, 10) == "normal"


def test_evaluate_reports_no_baseline_when_history_starts_inside_the_window() -> None:
    assert verdict(30, 0, 90, 9, history=BASELINE_FROM) == "insufficient_volume", "history on the first baseline day is a full baseline"
    assert verdict(30, 0, 90, 9, history=date(2026, 9, 2)) == "no_baseline"
    assert verdict(30, 0, 0, 0, history=None) == "no_baseline"
    assert verdict(30, 0, 90, 10, history=date(2026, 9, 20)) == "normal", "enough baseline volume is evaluated even when partial"


def test_evaluate_degrades_at_exactly_1000_basis_points() -> None:
    baseline = Outcomes(succeeded=9000, failed=1000)  # 9000 bp
    assert health.evaluate(Outcomes(8001, 1999), baseline, baseline_from=BASELINE_FROM, history_starts=HISTORY) == "normal"  # 8001 bp, drop 999
    assert health.evaluate(Outcomes(8000, 2000), baseline, baseline_from=BASELINE_FROM, history_starts=HISTORY) == "degraded"  # drop 1000
    assert health.drop_bp(Outcomes(8001, 1999), baseline) == 999 and health.drop_bp(Outcomes(8000, 2000), baseline) == 1000
    assert health.drop_bp(Outcomes(0, 0), baseline) is None and health.drop_bp(Outcomes(1, 1), Outcomes()) is None


def day(d: int, s: int, f: int, pending: int = 0) -> DayOutcomes:
    return DayOutcomes(succeeded=s, failed=f, pending=pending, day=date(2026, 10, d))


def test_worst_day_prefers_days_with_enough_volume_then_falls_back() -> None:
    assert health.worst_day([day(1, 9, 1), day(2, 17, 3), day(3, 1, 4)]) == day(2, 17, 3), "the 20% day has 5 completed and is skipped"
    assert health.worst_day([day(1, 5, 1), day(3, 1, 4)]) == day(3, 1, 4), "with no 10-completed day, any completed day qualifies"
    assert health.worst_day([day(1, 5, 5), day(2, 10, 10)]) == day(1, 5, 5), "ties go to the earlier day"
    assert health.worst_day([day(1, 0, 0, pending=3), day(2, 0, 0)]) is None
    assert health.worst_day([]) is None
    assert day(1, 4, 5).low_volume and not day(1, 5, 5).low_volume


def at(hour: int, minute: int = 0, second: int = 0) -> str:
    return to_iso(chicago_local(2026, 10, 1, hour, minute, second))


def test_recovery_state_window_is_one_hour_inclusive_from_the_first_attempt() -> None:
    assert health.recovery_state(succeeded_at=at(10, 30), latest_outcome="succeeded", first_attempt_at=at(10)) == "recovered_within_window"
    assert health.recovery_state(succeeded_at=at(11, 0, 0), latest_outcome="succeeded", first_attempt_at=at(10)) == "recovered_within_window"
    assert health.recovery_state(succeeded_at=at(11, 0, 1), latest_outcome="succeeded", first_attempt_at=at(10)) == "recovered_later"
    assert health.recovery_state(succeeded_at=None, latest_outcome="pending", first_attempt_at=at(10)) == "attempt_pending"
    assert health.recovery_state(succeeded_at=None, latest_outcome="failed", first_attempt_at=at(10)) == "unresolved"


def test_aggregate_status_is_the_worst_channel_verdict() -> None:
    assert health.aggregate_status(["normal", "degraded", "insufficient_volume"]) == "degraded"
    assert health.aggregate_status(["insufficient_volume", "normal", "no_baseline"]) == "normal"
    assert health.aggregate_status(["insufficient_volume", "no_baseline"]) == "no_baseline"
    assert health.aggregate_status(["insufficient_volume", "insufficient_volume"]) == "insufficient_volume"
    assert health.aggregate_status([]) == "insufficient_volume"


def test_rate_and_points_formatting_is_integer_half_up() -> None:
    assert health.format_rate_bp(7204) == "72.0%" and health.format_rate_bp(5579) == "55.8%" and health.format_rate_bp(9094) == "90.9%"
    assert health.format_rate_bp(10000) == "100.0%" and health.format_rate_bp(0) == "0.0%" and health.format_rate_bp(5) == "0.1%" and health.format_rate_bp(4) == "0.0%"
    assert health.format_points_bp(1875) == "18.8 pts" and health.format_points_bp(-1875) == "18.8 pts" and health.format_points_bp(1000) == "10.0 pts"
    assert health.format_points_bp(999) == "10.0 pts" and health.format_points_bp(994) == "9.9 pts" and health.format_points_bp(995) == "10.0 pts"
    assert health.format_points_bp(0) == "0.0 pts"


def test_day_labels_match_the_period_labels() -> None:
    assert health.day_label(date(2026, 10, 1)) == "Oct 1" and health.day_label(date(2026, 10, 1), with_year=True) == "Oct 1, 2026"
    for from_day, to_day in ((date(2026, 8, 7), date(2026, 9, 5)), (date(2026, 9, 27), date(2026, 9, 27)), (date(2025, 12, 30), date(2026, 1, 2))):
        start, end = "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"
        expected = periods.Period(preset="custom", from_day=from_day, to_day=to_day, start=start, end=end).range_label
        assert health.date_range_label(from_day, to_day) == expected
    assert health.date_range_label(date(2026, 8, 7), date(2026, 9, 5)) == "Aug 7 – Sep 5, 2026"


MOBILE = ChannelVerdict("mobile_app", "Mobile app", "degraded", Outcomes(134, 52, 1), Outcomes(572, 58), day(1, 25, 31))
WEBSITE = ChannelVerdict("website", "Website", "normal", Outcomes(246, 20, 1), Outcomes(969, 91))
IN_STORE = ChannelVerdict("in_store", "In store", "normal", Outcomes(119, 18), Outcomes(362, 33))


def test_degraded_copy_names_each_degraded_channel_with_its_worst_day() -> None:
    headline, detail = health.attention_text(
        "degraded", [WEBSITE, MOBILE, IN_STORE], scope_period=Outcomes(), scope_baseline=Outcomes(), baseline_from=date(2026, 8, 30), baseline_to=date(2026, 9, 28), history_starts=date(2026, 9, 5)
    )
    assert headline == "Attention needed: Mobile app payment performance degraded"
    assert detail == "Mobile app: 72.0% of completed attempts succeeded vs 90.8% in the baseline (18.8 pts lower). Worst day Oct 1: 44.6% of 56 completed attempts."
    two = ChannelVerdict("website", "Website", "degraded", Outcomes(70, 30), Outcomes(900, 100))
    assert health.degraded_headline(["Website", "Mobile app"]) == "Attention needed: Website and Mobile app payment performance degraded"
    assert health.degraded_detail([two, MOBILE]) == (
        "Website: 70.0% of completed attempts succeeded vs 90.0% in the baseline (20.0 pts lower). "
        "Mobile app: 72.0% of completed attempts succeeded vs 90.8% in the baseline (18.8 pts lower). Worst day Oct 1: 44.6% of 56 completed attempts."
    )


def test_normal_copy_lists_only_channels_with_a_normal_verdict() -> None:
    headline, detail = health.attention_text(
        "normal", [WEBSITE, ChannelVerdict("mobile_app", "Mobile app", "insufficient_volume", Outcomes(5, 2), Outcomes(90, 9)), IN_STORE],
        scope_period=Outcomes(), scope_baseline=Outcomes(), baseline_from=date(2026, 8, 30), baseline_to=date(2026, 9, 28), history_starts=date(2026, 9, 5),
    )
    assert headline == "No significant degradation detected for the selected scope"
    assert detail == (
        "Completed-attempt success is within 10.0 pts of the baseline for every channel with enough volume: Website 92.5% vs 91.4%, In store 86.9% vs 91.7%. "
        "Individual payments can still fail; the unresolved list shows which."
    )
    assert health.normal_detail([IN_STORE]).split(": ")[1].startswith("In store 86.9% vs 91.7%. ")


def test_insufficient_volume_copy_quotes_the_scope_counts_and_the_minimums() -> None:
    headline, detail = health.attention_text(
        "insufficient_volume", [], scope_period=Outcomes(3, 2), scope_baseline=Outcomes(111, 12), baseline_from=date(2026, 8, 28), baseline_to=date(2026, 9, 26), history_starts=date(2026, 9, 5)
    )
    assert headline == "Insufficient volume to evaluate payment health"
    assert detail == "5 completed attempts in the period (30 needed) and 123 in the baseline (100 needed). Counts are shown without a verdict."


def test_no_baseline_copy_names_where_history_starts() -> None:
    headline, detail = health.attention_text(
        "no_baseline", [], scope_period=Outcomes(2327, 263), scope_baseline=Outcomes(75, 9), baseline_from=date(2026, 8, 7), baseline_to=date(2026, 9, 5), history_starts=date(2026, 9, 5)
    )
    assert headline == "No baseline yet: payment history starts Sep 5, 2026"
    assert detail == (
        "The baseline would be Aug 7 – Sep 5, 2026, but recorded history begins Sep 5, 2026, leaving 84 completed attempts to compare against (100 needed). "
        "Period figures are shown without a verdict."
    )
    headline, detail = health.attention_text(
        "no_baseline", [], scope_period=Outcomes(), scope_baseline=Outcomes(), baseline_from=date(2026, 8, 7), baseline_to=date(2026, 9, 5), history_starts=None
    )
    assert headline == "No baseline yet: no recorded payment attempts"
    assert detail == "The baseline would be Aug 7 – Sep 5, 2026, but this business has no recorded payment attempts yet. Period figures are shown without a verdict."
