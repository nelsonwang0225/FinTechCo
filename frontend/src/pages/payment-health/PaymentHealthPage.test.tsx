import { afterEach, describe, expect, it } from "vitest";
import type { ChannelHealth, PaymentHealth } from "../../api/payment-health-types";
import type { PaymentListItem } from "../../api/payments-types";
import { META, PAYMENTS, PERIOD } from "../../test/fixtures";
import { MAYA, mockFetch, type Handler } from "../../test/mockApi";
import { click, flush, renderPage, setValue, type Rendered } from "../../test/render";
import { PaymentHealthPage } from "./PaymentHealthPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

const stats = (succeeded: number, failed: number, pending: number, rate: number | null) => ({ succeeded, failed, pending, completed: succeeded + failed, success_rate_bps: rate });

function channel(c: string, label: string, period: ReturnType<typeof stats>, baseline: ReturnType<typeof stats>, change: number | null, assessment: ChannelHealth["assessment"], assessmentLabel: string): ChannelHealth {
  return { channel: c, channel_label: label, period, baseline, change_bps: change, assessment, assessment_label: assessmentLabel };
}

const FAILED: PaymentListItem[] = PAYMENTS.items.map((p) => ({ ...p, status: "failed", status_label: "Failed" }));

const HEALTH: PaymentHealth = {
  as_of: "2026-10-05T14:12:00Z",
  period: PERIOD,
  baseline: { from_date: "2026-08-30", to_date: "2026-09-28", range_label: "Aug 30 – Sep 28, 2026", days: 30 },
  channel: null,
  thresholds: { min_completed_attempts: 30, degradation_points: 5, low_volume_day_attempts: 10, baseline_days: 30, recovery_window_minutes: 60 },
  summary: { period: stats(499, 90, 2, 8472), baseline: stats(1903, 182, 0, 9127), change_bps: -655, assessment: "degraded", assessment_label: "Degraded" },
  channels: [
    channel("website", "Website", stats(246, 20, 1, 9248), stats(969, 91, 0, 9142), 106, "not_degraded", "No significant degradation"),
    channel("mobile_app", "Mobile app", stats(134, 52, 1, 7204), stats(572, 58, 0, 9079), -1875, "degraded", "Degraded"),
    channel("in_store", "In store", stats(9, 1, 0, 9000), stats(20, 2, 0, 9091), -91, "insufficient_data", "Not enough data"),
  ],
  trend: [
    { date: "2026-09-29", succeeded: 75, failed: 4, pending: 0, completed: 79, success_rate_bps: 9494, low_volume: false },
    { date: "2026-09-30", succeeded: 0, failed: 0, pending: 0, completed: 0, success_rate_bps: null, low_volume: false },
    { date: "2026-10-01", succeeded: 84, failed: 38, pending: 0, completed: 122, success_rate_bps: 6885, low_volume: false },
    { date: "2026-10-05", succeeded: 6, failed: 1, pending: 2, completed: 7, success_rate_bps: 8571, low_volume: true },
  ],
  failure_signals: [
    { failure_code: "issuer_unavailable", label: "Issuer unavailable", failed_attempts: 32 },
    { failure_code: "do_not_honor", label: "Do not honor", failed_attempts: 58 },
  ],
  recovery: {
    affected_payments: 83,
    recovered_payments: 55,
    recovered_within_window_payments: 54,
    unresolved_payments: 28,
    awaiting_outcome_payments: 0,
    affected_value_cents: 2334007,
    recovered_value_cents: 1571734,
    unresolved_value_cents: 762273,
    awaiting_outcome_value_cents: 0,
    currency: "USD",
  },
  unresolved: { items: FAILED, total: 28 },
};

const EMPTY: PaymentHealth = {
  ...HEALTH,
  channel: "website",
  summary: { period: stats(0, 0, 3, null), baseline: stats(10, 1, 0, 9091), change_bps: null, assessment: "no_completed_attempts", assessment_label: "No completed attempts" },
  channels: HEALTH.channels.map((c) => ({ ...c, assessment: "no_completed_attempts" as const, assessment_label: "No completed attempts", period: stats(0, 0, c.channel === "website" ? 3 : 0, null), change_bps: null })),
  trend: HEALTH.trend.map((p) => ({ ...p, succeeded: 0, failed: 0, completed: 0, success_rate_bps: null, low_volume: false })),
  failure_signals: [],
  recovery: { ...HEALTH.recovery, affected_payments: 0, recovered_payments: 0, recovered_within_window_payments: 0, unresolved_payments: 0, affected_value_cents: 0, recovered_value_cents: 0, unresolved_value_cents: 0 },
  unresolved: { items: [], total: 0 },
};

function handlerFor(body: PaymentHealth | { status: number; body: unknown } = HEALTH): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: MAYA };
    if (url === "/api/meta") return { status: 200, body: META };
    if (url.startsWith("/api/payment-health")) return "status" in body ? body : { status: 200, body };
    return undefined;
  };
}

describe("PaymentHealthPage", () => {
  it("requests the default period and names the degraded channel with its rate, baseline and failed attempts", async () => {
    const { calls } = mockFetch(handlerFor());
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(calls.find((c) => c.url.startsWith("/api/payment-health"))?.url).toBe("/api/payment-health?period=last_7_days");
    expect(el.querySelector("h1")?.textContent).toBe("Payment health");
    const items = el.querySelectorAll(".attention-item");
    expect(items[0]?.textContent).toContain("Mobile app is degraded: 72.0% success vs a 90.8% baseline (−18.8 pts)");
    expect(items[0]?.textContent).toContain("52 failed of 186 completed attempts in Sep 29 – Oct 5, 2026");
    const unresolvedLink = items[0]?.querySelector("a")?.getAttribute("href");
    expect(unresolvedLink).toBe("/payments?period=last_7_days&channel=mobile_app&status=failed&return=%2Fpayment-health");
    expect(items[1]?.textContent).toContain("No significant degradation in Website");
    expect(items[2]?.textContent).toContain("In store: not enough data to evaluate");
    expect(items[2]?.textContent).toContain("each needs at least 30");
  });

  it("shows completed-attempt metrics against the baseline, with pending attempts counted but excluded", async () => {
    mockFetch(handlerFor());
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const text = page.container.textContent ?? "";
    expect(text).toContain("Success rate · All channels84.7%Baseline 91.3% · −6.6 pts");
    expect(text).toContain("Completed attempts589499 succeeded · 90 failed2 pending attempts excluded from the rate");
    expect(text).toContain("Unresolved payments28$7,622.73 in payment amounts");
    expect(text).not.toMatch(/lost revenue|root cause/i);
  });

  it("draws the trend with a baseline, a gap for a day with no completed attempts and a hollow low-volume point", async () => {
    mockFetch(handlerFor());
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const chart = page.container.querySelector("svg.line-chart");
    expect(chart?.querySelectorAll("path.chart-line").length).toBe(2);
    expect(chart?.querySelector(".chart-reference title")?.textContent).toBe("Baseline 91.3% (Aug 30 – Sep 28, 2026)");
    const points = chart?.querySelectorAll(".chart-point");
    expect(points?.[1]?.getAttribute("data-gap")).toBe("true");
    expect(points?.[1]?.querySelector("title")?.textContent).toBe("Sep 30: no completed attempts");
    expect(points?.[3]?.classList.contains("chart-point-low")).toBe(true);
    expect(points?.[3]?.querySelector("title")?.textContent).toBe("Oct 5: 85.7% success (low volume) · 6 succeeded, 1 failed, 2 pending");
    expect(page.container.querySelector(".chart-data tbody")?.textContent).toContain("No completed attempts");
  });

  it("scopes the page to a channel from its row and links failure signals to the matching failed attempts", async () => {
    const { calls } = mockFetch(handlerFor());
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=month_to_date");
    await flush();
    const el = page.container;
    const signal = Array.from(el.querySelectorAll(".signal-row a")).find((a) => a.textContent === "Issuer unavailable");
    expect(signal?.getAttribute("href")).toBe(
      "/payments?tab=attempts&period=month_to_date&outcome=failed&failure_code=issuer_unavailable&return=%2Fpayment-health%3Fperiod%3Dmonth_to_date",
    );
    expect(el.textContent).toContain("They describe what was reported, not a confirmed cause.");
    const review = Array.from(el.querySelectorAll("a")).find((a) => a.textContent?.startsWith("Review all 28 unresolved payments"));
    expect(review?.getAttribute("href")).toBe("/payments?period=month_to_date&status=failed&return=%2Fpayment-health%3Fperiod%3Dmonth_to_date");
    const mobile = Array.from(el.querySelectorAll("button.channel-select")).find((b) => b.textContent?.startsWith("Mobile app"));
    expect(mobile?.getAttribute("aria-pressed")).toBe("false");
    await click(mobile ?? null);
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=month_to_date&channel=mobile_app");
  });

  it("marks the selected channel and keeps channel and period in the URL", async () => {
    const { calls } = mockFetch(handlerFor({ ...HEALTH, channel: "mobile_app" }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?channel=mobile_app");
    await flush();
    const mobile = Array.from(page.container.querySelectorAll("button.channel-select")).find((b) => b.textContent?.startsWith("Mobile app"));
    expect(mobile?.getAttribute("aria-pressed")).toBe("true");
    expect(mobile?.textContent).toContain("Showing");
    await setValue(page.container.querySelector("#health-period-preset"), "last_30_days");
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=last_30_days&channel=mobile_app");
  });

  it("shows recovery by payment as payment amounts and lists the first unresolved payments", async () => {
    mockFetch(handlerFor());
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const text = page.container.textContent ?? "";
    expect(text).toContain("Affected payments83 · $23,340.07");
    expect(text).toContain("Recovered55 · $15,717.34");
    expect(text).toContain("Recovered within 60 minutes of the first attempt54");
    expect(text).toContain("Unresolved28 · $7,622.73");
    expect(text).toContain("Showing the newest 2 of 28.");
    expect(page.container.querySelector("a[href='/payments/pay_anchor00000001']")).not.toBeNull();
    expect(text).toContain("How these figures are defined");
    expect(text).toContain("at least 5 percentage points below the channel's baseline");
  });

  it("shows an empty state instead of a rate when nothing completed, and says how many are pending", async () => {
    mockFetch(handlerFor(EMPTY));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?channel=website");
    await flush();
    const text = page.container.textContent ?? "";
    expect(text).toContain("No completed attempts in this period");
    expect(text).toContain("3 attempts are still pending. No success rate is shown until attempts complete.");
    expect(page.container.querySelector("svg.line-chart")).toBeNull();
    expect(text).not.toContain("0.0%");
    expect(text).toContain("Website: no completed attempts in this period");
  });

  it("shows the forbidden and error states", async () => {
    mockFetch(handlerFor({ status: 403, body: { error: { code: "forbidden", message: "Your role does not include payments:read." } } }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.textContent).toContain("Your role does not include this section");
    page.unmount();
    mockFetch(handlerFor({ status: 500, body: { error: { code: "internal", message: "Something went wrong." } } }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.textContent).toContain("Could not load this view");
  });
});
