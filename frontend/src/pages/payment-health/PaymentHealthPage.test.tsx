import { afterEach, describe, expect, it } from "vitest";
import type { ChannelHealth, FailureSignal, PaymentHealth, TrendPoint } from "../../api/payment-health-types";
import { META, PERIOD } from "../../test/fixtures";
import { MAYA, mockFetch, type Handler } from "../../test/mockApi";
import { click, flush, renderPage, setValue, type Rendered } from "../../test/render";
import { PaymentHealthPage } from "./PaymentHealthPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

/* ------------------------------------------------------------------ fixtures: Alder & Loom as the API returns them */

const RULE = { baseline_days: 30, min_period_completed: 30, min_baseline_completed: 100, degraded_drop_bp: 1000, low_volume_day_completed: 10, recovery_window_minutes: 60 };
const AS_OF = "2026-10-05T14:12:00Z";

function outcomes(succeeded: number, failed: number, pending = 0) {
  const completed = succeeded + failed;
  const rate = (n: number) => (completed === 0 ? null : Math.floor((2 * 10000 * n + completed) / (2 * completed)));
  return { succeeded, failed, pending, completed, success_rate_bp: rate(succeeded), failed_share_bp: rate(failed) };
}

function day(d: string, succeeded: number, failed: number): TrendPoint {
  const o = outcomes(succeeded, failed);
  return { day: d, succeeded, failed, completed: o.completed, success_rate_bp: o.success_rate_bp, low_volume: o.completed < RULE.low_volume_day_completed };
}

const WEBSITE_7: ChannelHealth = {
  channel: "website",
  channel_label: "Website",
  status: "normal",
  status_label: "Normal",
  period: outcomes(246, 20, 1),
  baseline: outcomes(969, 91),
  drop_bp: -106,
  worst_day: day("2026-10-04", 32, 5),
};
const MOBILE_7: ChannelHealth = {
  channel: "mobile_app",
  channel_label: "Mobile app",
  status: "degraded",
  status_label: "Degraded",
  period: outcomes(134, 52, 1),
  baseline: outcomes(572, 58),
  drop_bp: 1875,
  worst_day: day("2026-10-01", 25, 31),
};
const IN_STORE_7: ChannelHealth = {
  channel: "in_store",
  channel_label: "In store",
  status: "normal",
  status_label: "Normal",
  period: outcomes(119, 18),
  baseline: outcomes(362, 33),
  drop_bp: 479,
  worst_day: day("2026-10-04", 17, 4),
};

const SIGNALS_7: FailureSignal[] = [
  { failure_code: "issuer_unavailable", label: "Issuer unavailable", count: 32, share_bp: 3556 },
  { failure_code: "do_not_honor", label: "Do not honor", count: 17, share_bp: 1889 },
  { failure_code: "insufficient_funds", label: "Insufficient funds", count: 13, share_bp: 1444 },
  { failure_code: "card_velocity_exceeded", label: "Card velocity exceeded", count: 6, share_bp: 667 },
  { failure_code: "incorrect_cvc", label: "Incorrect security code", count: 6, share_bp: 667 },
  { failure_code: "authentication_failed", label: "Authentication failed", count: 5, share_bp: 556 },
  { failure_code: "expired_card", label: "Expired card", count: 4, share_bp: 444 },
  { failure_code: "processing_error", label: "Processing error", count: 4, share_bp: 444 },
  { failure_code: "fraud_suspected", label: "Suspected fraud", count: 2, share_bp: 222 },
  { failure_code: "lost_or_stolen", label: "Card reported lost or stolen", count: 1, share_bp: 111 },
];

/** Last 7 days, all channels: Mobile app degraded, the other two normal. */
const LAST_7: PaymentHealth = {
  period: PERIOD,
  channel: null,
  channel_label: "All channels",
  as_of: AS_OF,
  rule: RULE,
  baseline: { from_date: "2026-08-30", to_date: "2026-09-28", range_label: "Aug 30 – Sep 28, 2026", history_starts: "2026-09-05", partial: true },
  attention: {
    status: "degraded",
    headline: "Attention needed: Mobile app payment performance degraded",
    detail: "Mobile app: 72.0% of completed attempts succeeded vs 90.8% in the baseline (18.8 pts lower). Worst day Oct 1: 44.6% of 56 completed attempts.",
    degraded_channels: ["mobile_app"],
  },
  scope: {
    channel: null,
    channel_label: "All channels",
    status: "degraded",
    status_label: "Degraded",
    period: outcomes(499, 90, 2),
    baseline: outcomes(1903, 182),
    drop_bp: 655,
    worst_day: day("2026-10-01", 84, 38),
  },
  channels: [WEBSITE_7, MOBILE_7, IN_STORE_7],
  trend: {
    points: [day("2026-09-29", 75, 4), day("2026-09-30", 89, 7), day("2026-10-01", 84, 38), day("2026-10-02", 81, 18), day("2026-10-03", 96, 9), day("2026-10-04", 62, 13), day("2026-10-05", 12, 1)],
    baseline_rate_bp: 9127,
  },
  failure_signals: { total_failed: 90, items: SIGNALS_7, primary: SIGNALS_7[0] ?? null },
  recovery: {
    affected: 83,
    recovered: 55,
    recovered_within_window: 55,
    recovered_later: 0,
    attempt_pending: 0,
    unresolved: 28,
    recovered_within_window_share_bp: 6627,
    affected_cents: 2334007,
    recovered_cents: 1571734,
    unresolved_cents: 762273,
    attempt_pending_cents: 0,
    currency: "USD",
  },
  unresolved_payments: {
    total: 28,
    items: [
      {
        id: "pay_2iiabkeme3d7eu",
        order_reference: "AL-12480",
        customer: { id: "cus_bjzqfcm7m2yuxf", full_name: "Casey Larsen", email: "casey.larsen@example.com", reference: "AL-C-0395" },
        amount_cents: 8600,
        currency: "USD",
        last_attempt_at: "2026-10-05T12:09:29Z",
        last_failure_code: "do_not_honor",
        last_failure_label: "Do not honor",
        attempt_count: 1,
      },
      {
        id: "pay_ufafs3cldyyodc",
        order_reference: "AL-12452",
        customer: { id: "cus_ozidhfysw3srj7", full_name: "Wren Reed", email: "wren.reed@example.com", reference: "AL-C-0279" },
        amount_cents: 4851,
        currency: "USD",
        last_attempt_at: "2026-10-04T22:47:31Z",
        last_failure_code: "fraud_suspected",
        last_failure_label: "Suspected fraud",
        attempt_count: 2,
      },
      {
        id: "pay_jmmreyognqg27r",
        order_reference: "AL-12439",
        customer: null,
        amount_cents: 57330,
        currency: "USD",
        last_attempt_at: "2026-10-04T20:13:35Z",
        last_failure_code: null,
        last_failure_label: null,
        attempt_count: 1,
      },
    ],
  },
};

const MOBILE_SIGNALS_7: FailureSignal[] = [
  { failure_code: "issuer_unavailable", label: "Issuer unavailable", count: 30, share_bp: 5769 },
  { failure_code: "do_not_honor", label: "Do not honor", count: 8, share_bp: 1538 },
  { failure_code: "insufficient_funds", label: "Insufficient funds", count: 6, share_bp: 1154 },
  { failure_code: "incorrect_cvc", label: "Incorrect security code", count: 4, share_bp: 769 },
  { failure_code: "card_velocity_exceeded", label: "Card velocity exceeded", count: 2, share_bp: 385 },
  { failure_code: "expired_card", label: "Expired card", count: 2, share_bp: 385 },
];

/** Last 7 days scoped to Mobile app: the same channels, the mobile daily series with a low-volume last day. */
const LAST_7_MOBILE: PaymentHealth = {
  ...LAST_7,
  channel: "mobile_app",
  channel_label: "Mobile app",
  scope: MOBILE_7,
  trend: {
    points: [day("2026-09-29", 19, 0), day("2026-09-30", 26, 4), day("2026-10-01", 25, 31), day("2026-10-02", 28, 11), day("2026-10-03", 18, 2), day("2026-10-04", 13, 4), day("2026-10-05", 5, 0)],
    baseline_rate_bp: 9079,
  },
  failure_signals: { total_failed: 52, items: MOBILE_SIGNALS_7, primary: MOBILE_SIGNALS_7[0] ?? null },
  recovery: {
    affected: 47,
    recovered: 31,
    recovered_within_window: 31,
    recovered_later: 0,
    attempt_pending: 0,
    unresolved: 16,
    recovered_within_window_share_bp: 6596,
    affected_cents: 1258843,
    recovered_cents: 777710,
    unresolved_cents: 481133,
    attempt_pending_cents: 0,
    currency: "USD",
  },
  unresolved_payments: { total: 16, items: LAST_7.unresolved_payments.items.slice(0, 2) },
};

const OCT_1_2 = { preset: "custom", label: "Custom range", from_date: "2026-10-01", to_date: "2026-10-02", range_label: "Oct 1 – Oct 2, 2026" };
const MOBILE_OCT: ChannelHealth = {
  channel: "mobile_app",
  channel_label: "Mobile app",
  status: "degraded",
  status_label: "Degraded",
  period: outcomes(53, 42),
  baseline: outcomes(617, 62),
  drop_bp: 3508,
  worst_day: day("2026-10-01", 25, 31),
};
const OCT_SIGNALS: FailureSignal[] = [
  { failure_code: "issuer_unavailable", label: "Issuer unavailable", count: 29, share_bp: 6905 },
  { failure_code: "do_not_honor", label: "Do not honor", count: 3, share_bp: 714 },
  { failure_code: "insufficient_funds", label: "Insufficient funds", count: 3, share_bp: 714 },
  { failure_code: "processing_error", label: "Processing error", count: 3, share_bp: 714 },
  { failure_code: "authentication_failed", label: "Authentication failed", count: 1, share_bp: 238 },
  { failure_code: "card_velocity_exceeded", label: "Card velocity exceeded", count: 1, share_bp: 238 },
  { failure_code: "expired_card", label: "Expired card", count: 1, share_bp: 238 },
  { failure_code: "incorrect_cvc", label: "Incorrect security code", count: 1, share_bp: 238 },
];

/** Custom Oct 1–2, Mobile app: the two days of the degradation. */
const OCT_MOBILE: PaymentHealth = {
  period: OCT_1_2,
  channel: "mobile_app",
  channel_label: "Mobile app",
  as_of: AS_OF,
  rule: RULE,
  baseline: { from_date: "2026-09-01", to_date: "2026-09-30", range_label: "Sep 1 – Sep 30, 2026", history_starts: "2026-09-05", partial: true },
  attention: {
    status: "degraded",
    headline: "Attention needed: Mobile app payment performance degraded",
    detail: "Mobile app: 55.8% of completed attempts succeeded vs 90.9% in the baseline (35.1 pts lower). Worst day Oct 1: 44.6% of 56 completed attempts.",
    degraded_channels: ["mobile_app"],
  },
  scope: MOBILE_OCT,
  channels: [
    { channel: "website", channel_label: "Website", status: "normal", status_label: "Normal", period: outcomes(72, 7), baseline: outcomes(1052, 96), drop_bp: 50, worst_day: day("2026-10-01", 37, 4) },
    MOBILE_OCT,
    { channel: "in_store", channel_label: "In store", status: "normal", status_label: "Normal", period: outcomes(40, 7), baseline: outcomes(398, 35), drop_bp: 681, worst_day: day("2026-10-02", 18, 4) },
  ],
  trend: { points: [day("2026-10-01", 25, 31), day("2026-10-02", 28, 11)], baseline_rate_bp: 9087 },
  failure_signals: { total_failed: 42, items: OCT_SIGNALS, primary: OCT_SIGNALS[0] ?? null },
  recovery: {
    affected: 38,
    recovered: 26,
    recovered_within_window: 26,
    recovered_later: 0,
    attempt_pending: 0,
    unresolved: 12,
    recovered_within_window_share_bp: 6842,
    affected_cents: 896010,
    recovered_cents: 473199,
    unresolved_cents: 422811,
    attempt_pending_cents: 0,
    currency: "USD",
  },
  unresolved_payments: {
    total: 12,
    items: [
      {
        id: "pay_54xujaox3j3tpp",
        order_reference: "AL-12298",
        customer: { id: "cus_rcfgq5osdn3i44", full_name: "Beatriz Kim", email: "beatriz.kim@example.com", reference: "AL-C-0047" },
        amount_cents: 98123,
        currency: "USD",
        last_attempt_at: "2026-10-03T01:41:18Z",
        last_failure_code: "do_not_honor",
        last_failure_label: "Do not honor",
        attempt_count: 1,
      },
      {
        id: "pay_k4plm4ktkgu4dh",
        order_reference: "AL-12247",
        customer: { id: "cus_gdccnyuehywegm", full_name: "Simone Lee", email: "simone.lee@example.com", reference: "AL-C-0050" },
        amount_cents: 103304,
        currency: "USD",
        last_attempt_at: "2026-10-02T17:18:25Z",
        last_failure_code: "insufficient_funds",
        last_failure_label: "Insufficient funds",
        attempt_count: 1,
      },
    ],
  },
};

/** Last 30 days: the baseline window starts before recorded history, so every channel is "no baseline yet". */
const LAST_30 = { preset: "last_30_days", label: "Last 30 days", from_date: "2026-09-06", to_date: "2026-10-05", range_label: "Sep 6 – Oct 5, 2026" };
function noBaseline(c: ChannelHealth, period: ReturnType<typeof outcomes>, baseline: ReturnType<typeof outcomes>): ChannelHealth {
  return { ...c, status: "no_baseline", status_label: "No baseline yet", period, baseline, drop_bp: null };
}
const NO_BASELINE: PaymentHealth = {
  ...LAST_7,
  period: LAST_30,
  baseline: { from_date: "2026-08-07", to_date: "2026-09-05", range_label: "Aug 7 – Sep 5, 2026", history_starts: "2026-09-05", partial: true },
  attention: {
    status: "no_baseline",
    headline: "No baseline yet: payment history starts Sep 5, 2026",
    detail: "The baseline would be Aug 7 – Sep 5, 2026, but recorded history begins Sep 5, 2026, leaving 84 completed attempts to compare against (100 needed). Period figures are shown without a verdict.",
    degraded_channels: [],
  },
  scope: noBaseline(LAST_7.scope, outcomes(2327, 263, 2), outcomes(75, 9)),
  channels: [noBaseline(WEBSITE_7, outcomes(1183, 106, 1), outcomes(32, 5)), noBaseline(MOBILE_7, outcomes(685, 108, 1), outcomes(21, 2)), noBaseline(IN_STORE_7, outcomes(459, 49), outcomes(22, 2))],
  trend: { points: [day("2026-09-28", 87, 11), day("2026-09-29", 75, 4), day("2026-09-30", 89, 7), day("2026-10-01", 84, 38), day("2026-10-02", 81, 18)], baseline_rate_bp: null },
};

/** A single quiet day on a small channel: five completed attempts, so no verdict. */
const SEP_27 = { preset: "custom", label: "Custom range", from_date: "2026-09-27", to_date: "2026-09-27", range_label: "Sep 27, 2026" };
const INSUFFICIENT: PaymentHealth = {
  ...OCT_MOBILE,
  period: SEP_27,
  baseline: { from_date: "2026-08-28", to_date: "2026-09-26", range_label: "Aug 28 – Sep 26, 2026", history_starts: "2026-09-05", partial: true },
  attention: {
    status: "insufficient_volume",
    headline: "Insufficient volume to evaluate payment health",
    detail: "5 completed attempts in the period (30 needed) and 140 in the baseline (100 needed). Counts are shown without a verdict.",
    degraded_channels: [],
  },
  scope: { ...MOBILE_OCT, status: "insufficient_volume", status_label: "Insufficient volume", period: outcomes(3, 2), baseline: outcomes(126, 14), drop_bp: 3000, worst_day: day("2026-09-27", 3, 2) },
  channels: [
    { ...OCT_MOBILE.channels[0]!, status: "insufficient_volume", status_label: "Insufficient volume", period: outcomes(6, 1), drop_bp: null },
    { ...MOBILE_OCT, status: "insufficient_volume", status_label: "Insufficient volume", period: outcomes(3, 2), baseline: outcomes(126, 14), drop_bp: 3000 },
    { ...OCT_MOBILE.channels[2]!, status: "insufficient_volume", status_label: "Insufficient volume", period: outcomes(4, 0), drop_bp: null },
  ],
  trend: { points: [day("2026-09-27", 3, 2)], baseline_rate_bp: null },
  failure_signals: { total_failed: 2, items: [{ failure_code: "do_not_honor", label: "Do not honor", count: 2, share_bp: 10000 }], primary: { failure_code: "do_not_honor", label: "Do not honor", count: 2, share_bp: 10000 } },
  recovery: { ...OCT_MOBILE.recovery, affected: 2, recovered: 1, recovered_within_window: 1, unresolved: 1, recovered_within_window_share_bp: 5000, affected_cents: 12000, recovered_cents: 7000, unresolved_cents: 5000 },
  unresolved_payments: { total: 1, items: OCT_MOBILE.unresolved_payments.items.slice(0, 1) },
};

/** Today only, a channel with two attempts still pending and nothing completed. */
const OCT_5 = { preset: "custom", label: "Custom range", from_date: "2026-10-05", to_date: "2026-10-05", range_label: "Oct 5, 2026" };
const NOTHING_COMPLETED: PaymentHealth = {
  ...INSUFFICIENT,
  period: OCT_5,
  channel: "website",
  channel_label: "Website",
  attention: {
    status: "insufficient_volume",
    headline: "Insufficient volume to evaluate payment health",
    detail: "0 completed attempts in the period (30 needed) and 140 in the baseline (100 needed). Counts are shown without a verdict.",
    degraded_channels: [],
  },
  scope: { ...INSUFFICIENT.scope, channel: "website", channel_label: "Website", period: outcomes(0, 0, 2), worst_day: null },
  trend: { points: [{ day: "2026-10-05", succeeded: 0, failed: 0, completed: 0, success_rate_bp: null, low_volume: true }], baseline_rate_bp: null },
  failure_signals: { total_failed: 0, items: [], primary: null },
  recovery: { ...INSUFFICIENT.recovery, affected: 0, recovered: 0, recovered_within_window: 0, unresolved: 0, recovered_within_window_share_bp: null, affected_cents: 0, recovered_cents: 0, unresolved_cents: 0 },
  unresolved_payments: { total: 0, items: [] },
};

/** A day where every completed attempt succeeded. */
const SEP_29 = { preset: "custom", label: "Custom range", from_date: "2026-09-29", to_date: "2026-09-29", range_label: "Sep 29, 2026" };
const NOTHING_FAILED: PaymentHealth = {
  ...INSUFFICIENT,
  period: SEP_29,
  attention: {
    status: "insufficient_volume",
    headline: "Insufficient volume to evaluate payment health",
    detail: "19 completed attempts in the period (30 needed) and 140 in the baseline (100 needed). Counts are shown without a verdict.",
    degraded_channels: [],
  },
  scope: { ...INSUFFICIENT.scope, period: outcomes(19, 0), worst_day: day("2026-09-29", 19, 0) },
  trend: { points: [day("2026-09-29", 19, 0)], baseline_rate_bp: null },
  failure_signals: { total_failed: 0, items: [], primary: null },
  recovery: { ...NOTHING_COMPLETED.recovery },
  unresolved_payments: { total: 0, items: [] },
};

function handlerFor(health: PaymentHealth | ((url: string) => PaymentHealth)): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: MAYA };
    if (url === "/api/meta") return { status: 200, body: META };
    if (url.startsWith("/api/payment-health")) return { status: 200, body: typeof health === "function" ? health(url) : health };
    return undefined;
  };
}

function text(): string {
  return page?.container.textContent ?? "";
}

function linkByText(label: string): HTMLAnchorElement | null {
  return Array.from(page?.container.querySelectorAll("a") ?? []).find((a) => a.textContent?.trim() === label) ?? null;
}

function cardByLabel(label: string): Element | null {
  return page?.container.querySelector(`section[aria-label='${label}']`) ?? null;
}

describe("PaymentHealthPage", () => {
  it("requests the last 7 days by default and renders the header, scope line and pending note", async () => {
    const { calls } = mockFetch(handlerFor(LAST_7));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(calls.find((c) => c.url.startsWith("/api/payment-health"))?.url).toBe("/api/payment-health?period=last_7_days");
    expect(page.container.querySelector("h1")?.textContent).toBe("Payment Health");
    expect(text()).toContain("Understand payment performance and investigate degradation.");
    expect(page.container.querySelector(".health-scope")?.textContent).toBe("All channels · Sep 29 – Oct 5, 2026 · As of Oct 5, 2026, 9:12:00 AM CDT");
    expect(page.container.querySelector(".health-pending")?.textContent).toBe("2 attempts are still pending; figures may change.");
    expect(page.container.querySelector<HTMLSelectElement>("#health-period-preset")?.value).toBe("last_7_days");
    expect(page.container.querySelector<HTMLSelectElement>("#health-channel")?.value).toBe("");
  });

  it("shows the attention summary with its badge and a review button scoped to the degraded channel", async () => {
    mockFetch(handlerFor(LAST_7));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const card = page.container.querySelector(".health-attention");
    expect(card?.getAttribute("role")).toBe("status");
    expect(card?.classList.contains("health-attention-danger")).toBe(true);
    expect(card?.querySelector("h2")?.textContent).toBe("Attention needed: Mobile app payment performance degraded");
    expect(card?.textContent).toContain("Worst day Oct 1: 44.6% of 56 completed attempts.");
    expect(card?.querySelector(".badge")?.textContent).toBe("Degraded");
    expect(card?.querySelector(".badge")?.classList.contains("badge-danger")).toBe(true);
    // The scope is all channels; the button lands on the first degraded channel's failed payments.
    expect(linkByText("Review unresolved payments")?.getAttribute("href")).toBe("/payments?period=last_7_days&channel=mobile_app&status=failed&ph_period=last_7_days&ph_channel=mobile_app");
  });

  it("renders the four KPI cards for a degraded channel with baseline comparison and level tags", async () => {
    const { calls } = mockFetch(handlerFor(LAST_7_MOBILE));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?channel=mobile_app");
    await flush();
    expect(calls.find((c) => c.url.startsWith("/api/payment-health"))?.url).toBe("/api/payment-health?period=last_7_days&channel=mobile_app");
    const t = text();
    expect(t).toContain("Attempt success rate72.0%vs 90.8% baseline (−18.8 pts)Baseline: Aug 30 – Sep 28, 2026, history from Sep 5, 2026");
    expect(t).toContain("Failed attempts5228.0% of 186 completed attempts");
    expect(t).toContain("Affected payments4731 recovered · 16 unresolved");
    expect(t).toContain("Affected payment value$12,588.43$7,777.10 recovered · $4,811.33 unresolved");
    const levels = Array.from(page.container.querySelectorAll(".health-kpi .health-level")).map((el) => el.textContent);
    expect(levels).toEqual(["Attempt-level", "Attempt-level", "Payment-level", "Payment-level"]);
    expect(page.container.querySelector(".health-scope")?.textContent).toContain("Mobile app · Sep 29 – Oct 5, 2026");
    expect(page.container.querySelector<HTMLSelectElement>("#health-channel")?.value).toBe("mobile_app");
  });

  it("draws the daily success-rate chart with a baseline, a low-volume marker and a gap for a day without completed attempts", async () => {
    const withGap: PaymentHealth = {
      ...LAST_7_MOBILE,
      trend: { ...LAST_7_MOBILE.trend, points: LAST_7_MOBILE.trend.points.map((p) => (p.day === "2026-10-03" ? { ...p, succeeded: 0, failed: 0, completed: 0, success_rate_bp: null, low_volume: true } : p)) },
    };
    mockFetch(handlerFor(withGap));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?channel=mobile_app");
    await flush();
    const chart = page.container.querySelector(".chart-card");
    expect(chart?.querySelector("h2")?.textContent).toBe("Payment performance over time");
    expect(chart?.querySelector(".section-aside")?.textContent).toBe("72.0% of completed attempts succeeded · Sep 29 – Oct 5, 2026");
    const svg = chart?.querySelector("svg[role=img]");
    expect(svg?.querySelector("title")?.textContent).toBe("Daily completed-attempt success rate, Mobile app, Sep 29 – Oct 5, 2026");
    expect(svg?.querySelectorAll(".chart-point").length).toBe(6);
    expect(svg?.querySelectorAll("path.chart-line").length).toBe(2);
    expect(svg?.querySelectorAll(".chart-point-low").length).toBe(1);
    const tooltips = Array.from(svg?.querySelectorAll(".chart-point-group title") ?? []).map((el) => el.textContent);
    expect(tooltips[2]).toBe("Oct 1: 44.6% · 31 failed of 56 completed");
    expect(tooltips[5]).toBe("Oct 5: 100.0% · 0 failed of 5 completed");
    expect(svg?.querySelector("desc")?.textContent).toContain("Oct 3: no completed attempts");
    expect(svg?.querySelector(".chart-baseline")).not.toBeNull();
    expect(svg?.querySelector(".chart-baseline-label")?.textContent).toBe("Baseline 90.8%");
    expect(chart?.querySelector(".chart-legend")?.textContent).toBe("Fewer than 10 completed attempts");
    const ticks = Array.from(svg?.querySelectorAll(".chart-tick") ?? []).map((el) => el.textContent);
    expect(ticks).toEqual(["0%", "25%", "50%", "75%", "100%"]);
  });

  it("draws all seven markers without a gap when every day has completed attempts", async () => {
    mockFetch(handlerFor(LAST_7_MOBILE));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?channel=mobile_app");
    await flush();
    const svg = page.container.querySelector(".chart-card svg[role=img]");
    expect(svg?.querySelectorAll(".chart-point").length).toBe(7);
    expect(svg?.querySelectorAll("path.chart-line").length).toBe(1);
  });

  it("lists every channel with its status, marks the selected one and selects a channel on row click", async () => {
    const { calls } = mockFetch(handlerFor((url) => (url.includes("channel=mobile_app") ? LAST_7_MOBILE : LAST_7)));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const table = page.container.querySelector(".health-channels table");
    const rows = Array.from(table?.querySelectorAll("tbody tr") ?? []);
    expect(rows.length).toBe(3);
    expect(rows.map((r) => r.querySelector("td")?.textContent)).toEqual(["Website", "Mobile app", "In store"]);
    expect(rows.map((r) => r.querySelector(".badge")?.textContent)).toEqual(["Normal", "Degraded", "Normal"]);
    expect(rows[1]?.textContent).toContain("72.0%");
    expect(rows[1]?.textContent).toContain("90.8%");
    expect(rows[1]?.textContent).toContain("186");
    expect(rows[1]?.querySelector("a")?.getAttribute("href")).toBe("/payment-health?channel=mobile_app");
    expect(table?.querySelector("a[aria-current]")).toBeNull();

    await click(rows[1]);
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=last_7_days&channel=mobile_app");
    const selected = page.container.querySelector(".health-channels a[aria-current='true']");
    expect(selected?.textContent).toBe("Mobile app");
  });

  it("changes the channel from the filter and keeps it in the URL request", async () => {
    const { calls } = mockFetch(handlerFor(LAST_7));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    await setValue(page.container.querySelector("#health-channel"), "in_store");
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=last_7_days&channel=in_store");
    await setValue(page.container.querySelector("#health-period-preset"), "month_to_date");
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=month_to_date&channel=in_store");
  });

  it("lists recorded failure signals with the primary signal and links each to the failed attempts of the scope", async () => {
    mockFetch(handlerFor(LAST_7));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const card = page.container.querySelector(".health-signals");
    expect(card?.querySelector("h2")?.textContent).toContain("Recorded failure signals");
    expect(card?.querySelector(".health-primary")?.textContent).toBe("Primary recorded signal: Issuer unavailable accounts for 35.6% of failed attempts in this scope.");
    const rows = Array.from(card?.querySelectorAll("tbody tr") ?? []);
    expect(rows.length).toBe(10);
    expect(rows[0]?.textContent).toContain("Issuer unavailable");
    expect(rows[0]?.querySelector(".mono")?.textContent).toBe("issuer_unavailable");
    expect(rows[0]?.querySelectorAll("td")[1]?.textContent).toBe("32");
    expect(rows[0]?.querySelectorAll("td")[2]?.textContent).toBe("35.6%");
    expect(rows[0]?.querySelector("a")?.textContent).toBe("View attempts");
    expect(rows[0]?.querySelector("a")?.getAttribute("href")).toBe("/payments?tab=attempts&period=last_7_days&outcome=failed&failure_code=issuer_unavailable&ph_period=last_7_days");
    expect(rows[9]?.querySelector("a")?.getAttribute("href")).toBe("/payments?tab=attempts&period=last_7_days&outcome=failed&failure_code=lost_or_stolen&ph_period=last_7_days");
  });

  it("carries custom dates and the channel on every drill-down link", async () => {
    const { calls } = mockFetch(handlerFor(OCT_MOBILE));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app");
    await flush();
    expect(calls.find((c) => c.url.startsWith("/api/payment-health"))?.url).toBe("/api/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app");
    expect(linkByText("Review unresolved payments")?.getAttribute("href")).toBe(
      "/payments?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app&status=failed&ph_period=custom&ph_from=2026-10-01&ph_to=2026-10-02&ph_channel=mobile_app",
    );
    const signalRow = page.container.querySelector(".health-signals tbody tr");
    expect(signalRow?.querySelector("a")?.getAttribute("href")).toBe(
      "/payments?tab=attempts&period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app&outcome=failed&failure_code=issuer_unavailable&ph_period=custom&ph_from=2026-10-01&ph_to=2026-10-02&ph_channel=mobile_app",
    );
    expect(linkByText("Review all 12 unresolved payments")?.getAttribute("href")).toBe(
      "/payments?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app&status=failed&ph_period=custom&ph_from=2026-10-01&ph_to=2026-10-02&ph_channel=mobile_app",
    );
    expect(text()).toContain("Attempt success rate55.8%vs 90.9% baseline (−35.1 pts)Baseline: Sep 1 – Sep 30, 2026, history from Sep 5, 2026");
    expect(text()).toContain("Primary recorded signal: Issuer unavailable accounts for 69.1% of failed attempts in this scope.");
  });

  it("shows the recovery flow, the value card and the unresolved payments with links to each payment", async () => {
    mockFetch(handlerFor(OCT_MOBILE));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app");
    await flush();
    const steps = Array.from(page.container.querySelectorAll(".health-flow li")).map((li) => li.textContent);
    expect(steps).toEqual(["Affected payments 38", "Recovered within 1 hour 26 (68.4%)", "Unresolved 12"]);
    expect(page.container.querySelector(".health-recovery")?.textContent).toContain("Counted once per payment. A payment declined twice and then completed is one affected payment and one recovered payment.");
    const value = page.container.querySelector(".health-value");
    expect(value?.textContent).toContain("Affected$8,960.10");
    expect(value?.textContent).toContain("Recovered$4,731.99");
    expect(value?.textContent).toContain("Unresolved$4,228.11");
    expect(value?.textContent).toContain("Payment amount counted once per payment.");
    const rows = Array.from(page.container.querySelectorAll(".health-unresolved tbody tr"));
    expect(rows.length).toBe(2);
    expect(rows[0]?.querySelector("a")?.getAttribute("href")).toBe("/payments/pay_54xujaox3j3tpp");
    expect(rows[0]?.querySelector("a")?.textContent).toBe("AL-12298");
    expect(rows[0]?.textContent).toContain("Beatriz Kim");
    expect(rows[0]?.textContent).toContain("$981.23");
    expect(rows[0]?.textContent).toContain("3 days ago");
    expect(rows[0]?.textContent).toContain("Do not honor");
    expect(rows[0]?.querySelectorAll("td")[5]?.textContent).toBe("1");
  });

  it("names a guest customer, a missing signal and extra recovery states when they occur", async () => {
    const withLater: PaymentHealth = {
      ...LAST_7,
      recovery: { ...LAST_7.recovery, recovered: 58, recovered_later: 3, attempt_pending: 2, unresolved: 23, attempt_pending_cents: 9000 },
    };
    mockFetch(handlerFor(withLater));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const steps = Array.from(page.container.querySelectorAll(".health-flow li")).map((li) => li.textContent);
    expect(steps).toEqual(["Affected payments 83", "Recovered within 1 hour 55 (66.3%)", "Recovered after 1 hour 3", "Attempt pending 2", "Unresolved 23"]);
    expect(text()).toContain("Affected payments8358 recovered · 23 unresolved · 2 attempt pending");
    const rows = Array.from(page.container.querySelectorAll(".health-unresolved tbody tr"));
    expect(rows[2]?.textContent).toContain("Guest");
    expect(rows[2]?.querySelectorAll("td")[4]?.textContent).toBe("—");
    expect(linkByText("Review all 28 unresolved payments")?.getAttribute("href")).toBe("/payments?period=last_7_days&status=failed&ph_period=last_7_days");
  });

  it("explains a missing baseline without reading as low volume", async () => {
    mockFetch(handlerFor(NO_BASELINE));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=last_30_days");
    await flush();
    const card = page.container.querySelector(".health-attention");
    expect(card?.querySelector("h2")?.textContent).toBe("No baseline yet: payment history starts Sep 5, 2026");
    expect(card?.textContent).toContain("Period figures are shown without a verdict.");
    expect(card?.querySelector(".badge")?.textContent).toBe("No baseline yet");
    expect(card?.querySelector(".badge")?.classList.contains("badge-neutral")).toBe(true);
    expect(card?.classList.contains("health-attention-neutral")).toBe(true);
    expect(linkByText("Review unresolved payments")).toBeNull();
    expect(text()).toContain("Attempt success rate89.9%No baseline yet");
    expect(text()).not.toContain("Insufficient volume");
    expect(page.container.querySelector(".chart-baseline")).toBeNull();
    const badges = Array.from(page.container.querySelectorAll(".health-channels .badge")).map((b) => b.textContent);
    expect(badges).toEqual(["No baseline yet", "No baseline yet", "No baseline yet"]);
  });

  it("shows raw counts without a verdict when the period has too few completed attempts", async () => {
    mockFetch(handlerFor(INSUFFICIENT));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=custom&from=2026-09-27&to=2026-09-27&channel=mobile_app");
    await flush();
    const card = page.container.querySelector(".health-attention");
    expect(card?.querySelector("h2")?.textContent).toBe("Insufficient volume to evaluate payment health");
    expect(card?.querySelector(".badge")?.textContent).toBe("Insufficient volume");
    expect(linkByText("Review unresolved payments")).toBeNull();
    expect(text()).toContain("Attempt success rate60.0%5 completed attempts; 30 needed to evaluate");
    expect(text()).toContain("Failed attempts240.0% of 5 completed attempts");
    expect(page.container.querySelector(".chart-card svg[role=img]")).not.toBeNull();
    expect(page.container.querySelector(".chart-baseline")).toBeNull();
  });

  it("collapses to an empty state plus the channel table when nothing completed", async () => {
    mockFetch(handlerFor(NOTHING_COMPLETED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=custom&from=2026-10-05&to=2026-10-05&channel=website");
    await flush();
    expect(page.container.querySelector(".state-empty .state-title")?.textContent).toBe("No completed attempts in this period");
    expect(page.container.querySelector(".state-empty")?.textContent).toContain("2 attempts are still pending");
    expect(page.container.querySelector(".health-pending")?.textContent).toBe("2 attempts are still pending; figures may change.");
    expect(page.container.querySelector(".health-channels table")).not.toBeNull();
    expect(page.container.querySelector(".health-attention")).toBeNull();
    expect(page.container.querySelector(".health-kpi")).toBeNull();
    expect(page.container.querySelector(".chart-card")).toBeNull();
    expect(page.container.querySelector(".health-signals")).toBeNull();
    expect(page.container.querySelector(".health-unresolved")).toBeNull();
  });

  it("keeps the chart and collapses the failure sections when nothing failed", async () => {
    mockFetch(handlerFor(NOTHING_FAILED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=custom&from=2026-09-29&to=2026-09-29&channel=mobile_app");
    await flush();
    expect(page.container.querySelector(".chart-card svg[role=img]")).not.toBeNull();
    expect(page.container.querySelector(".health-kpi")).not.toBeNull();
    expect(text()).toContain("Failed attempts00.0% of 19 completed attempts");
    expect(page.container.querySelector(".health-none")?.textContent).toBe("No failed attempts in the selected period");
    expect(page.container.querySelector(".health-signals")).toBeNull();
    expect(page.container.querySelector(".health-recovery")).toBeNull();
    expect(page.container.querySelector(".health-value")).toBeNull();
    expect(page.container.querySelector(".health-unresolved")).toBeNull();
    expect(page.container.querySelector(".health-pending")).toBeNull();
  });

  it("carries the definitions as reachable tooltips and never uses verdict language beyond the status labels", async () => {
    mockFetch(handlerFor(LAST_7));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const tips = Array.from(page.container.querySelectorAll("[role=tooltip]")).map((el) => el.textContent);
    expect(tips).toEqual([
      "Percentage of completed payment attempts that succeeded. Pending attempts are excluded.",
      "Payments in this period with at least one failed attempt, counted once per payment however many attempts it took.",
      "Reason recorded on the failed attempt. It doesn't necessarily establish the underlying cause.",
      "An affected payment that later succeeded. Within 1 hour means the successful attempt completed no more than an hour after the payment's first attempt was created.",
    ]);
    const buttons = Array.from(page.container.querySelectorAll("button.infotip-button"));
    expect(buttons.length).toBe(4);
    for (const button of buttons) {
      expect(button.getAttribute("type")).toBe("button");
      expect(button.getAttribute("aria-label")).toBeTruthy();
      const described = page.container.querySelector(`[id='${button.getAttribute("aria-describedby")}']`);
      expect(described?.getAttribute("role")).toBe("tooltip");
    }
    const lower = text().toLowerCase();
    expect(lower).not.toContain("root cause");
    expect(lower).not.toContain("revenue");
    expect(lower).not.toContain("outage");
    expect(lower).not.toContain("incident");
    expect(cardByLabel("Attempt success rate")).not.toBeNull();
  });

  it("renders the forbidden and error states", async () => {
    mockFetch((url) => {
      if (url === "/api/session") return { status: 200, body: MAYA };
      if (url === "/api/meta") return { status: 200, body: META };
      if (url.startsWith("/api/payment-health")) return { status: 403, body: { error: { code: "forbidden", message: "Your role does not include this." } } };
      return undefined;
    });
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(text()).toContain("Your role does not include this section");
    expect(page.container.querySelector(".health")).toBeNull();
  });
});
