import { afterEach, describe, expect, it } from "vitest";
import type { ChannelHealth, PaymentHealth } from "../../api/payment-health-types";
import { META, PAYMENTS, PERIOD } from "../../test/fixtures";
import { MAYA, mockFetch, type Handler } from "../../test/mockApi";
import { click, flush, renderPage, setValue, type Rendered } from "../../test/render";
import { PaymentHealthPage } from "./PaymentHealthPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

const RULES = { baseline_days: 30, degraded_drop_bp: 1000, min_period_completed: 50, min_baseline_completed: 100, low_volume_day_completed: 10, quick_recovery_seconds: 3600 };

function channel(partial: Partial<ChannelHealth> & Pick<ChannelHealth, "channel" | "channel_label" | "assessment" | "assessment_label">): ChannelHealth {
  return {
    completed: 100,
    succeeded: 92,
    failed: 8,
    pending: 0,
    success_rate_bp: 9200,
    baseline_completed: 400,
    baseline_succeeded: 364,
    baseline_rate_bp: 9100,
    change_bp: 100,
    ...partial,
  };
}

const DEGRADED: PaymentHealth = {
  period: PERIOD,
  baseline: { from_date: "2026-08-30", to_date: "2026-09-28", range_label: "Aug 30 – Sep 28, 2026", days: 30, days_with_completed: 24 },
  channel: null,
  channel_label: null,
  rules: RULES,
  attempts: { completed: 589, succeeded: 499, failed: 90, pending: 2, success_rate_bp: 8472, baseline_completed: 2085, baseline_succeeded: 1898, baseline_rate_bp: 9103, change_bp: -631 },
  attention: { state: "degraded", label: "Degradation detected", degraded_channels: ["mobile_app"], not_assessed_channels: [] },
  channels: [
    channel({ channel: "website", channel_label: "Website", assessment: "no_significant_degradation", assessment_label: "No significant degradation", completed: 266, succeeded: 246, failed: 20, pending: 1, success_rate_bp: 9248, baseline_rate_bp: 9142, change_bp: 106 }),
    channel({ channel: "mobile_app", channel_label: "Mobile app", assessment: "degraded", assessment_label: "Degraded", completed: 186, succeeded: 134, failed: 52, pending: 1, success_rate_bp: 7204, baseline_completed: 630, baseline_rate_bp: 9083, change_bp: -1879 }),
    channel({ channel: "in_store", channel_label: "In store", assessment: "no_significant_degradation", assessment_label: "No significant degradation", completed: 137, succeeded: 119, failed: 18, success_rate_bp: 8686, baseline_rate_bp: 9165, change_bp: -479 }),
  ],
  trend: [
    { day: "2026-09-29", completed: 80, succeeded: 76, failed: 4, pending: 0, success_rate_bp: 9500, low_volume: false },
    { day: "2026-09-30", completed: 0, succeeded: 0, failed: 0, pending: 0, success_rate_bp: null, low_volume: false },
    { day: "2026-10-01", completed: 8, succeeded: 4, failed: 4, pending: 1, success_rate_bp: 5000, low_volume: true },
  ],
  failure_signals: [
    { code: "issuer_unavailable", label: "Issuer unavailable", count: 31 },
    { code: "do_not_honor", label: "Do not honor", count: 20 },
  ],
  recovery: {
    currency: "USD",
    affected: { payments: 71, amount_cents: 2104512 },
    recovered: { payments: 50, amount_cents: 1380044 },
    recovered_within_hour: { payments: 50, amount_cents: 1380044 },
    unresolved: { payments: 21, amount_cents: 724468 },
    in_progress: { payments: 0, amount_cents: 0 },
  },
};

const QUIET: PaymentHealth = {
  ...DEGRADED,
  attention: { state: "no_significant_degradation", label: "No significant degradation detected", degraded_channels: [], not_assessed_channels: ["in_store"] },
  channels: DEGRADED.channels.map((c) => (c.channel === "mobile_app" ? { ...c, assessment: "no_significant_degradation", assessment_label: "No significant degradation" } : c.channel === "in_store" ? { ...c, assessment: "insufficient_volume", assessment_label: "Not enough volume to assess" } : c)),
};

const EMPTY: PaymentHealth = {
  ...DEGRADED,
  attempts: { completed: 0, succeeded: 0, failed: 0, pending: 2, success_rate_bp: null, baseline_completed: 0, baseline_succeeded: 0, baseline_rate_bp: null, change_bp: null },
  attention: { state: "no_completed_attempts", label: "No completed attempts in this period", degraded_channels: [], not_assessed_channels: [] },
  channels: [],
  trend: [{ day: "2026-10-05", completed: 0, succeeded: 0, failed: 0, pending: 2, success_rate_bp: null, low_volume: false }],
  failure_signals: [],
  recovery: { ...DEGRADED.recovery, affected: { payments: 0, amount_cents: 0 }, recovered: { payments: 0, amount_cents: 0 }, recovered_within_hour: { payments: 0, amount_cents: 0 }, unresolved: { payments: 0, amount_cents: 0 } },
};

function handlerFor(health: PaymentHealth | { status: number; body: unknown }): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: MAYA };
    if (url === "/api/meta") return { status: 200, body: META };
    if (url.startsWith("/api/payment-health")) return "status" in health ? health : { status: 200, body: health };
    if (url.startsWith("/api/payments?")) return { status: 200, body: { ...PAYMENTS, total: 21 } };
    return undefined;
  };
}

function hrefOf(el: HTMLElement, text: string): URL {
  const link = Array.from(el.querySelectorAll("a")).find((a) => a.textContent?.includes(text));
  if (!link) throw new Error(`no link ${text}`);
  return new URL(link.getAttribute("href") ?? "", "http://x");
}

describe("PaymentHealthPage", () => {
  it("names the degraded channel with its rate, baseline and failed attempts, and links to its unresolved payments", async () => {
    const { calls } = mockFetch(handlerFor(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(calls.find((c) => c.url.startsWith("/api/payment-health"))?.url).toBe("/api/payment-health?period=last_7_days");
    const attention = el.querySelector(".health-attention")!;
    expect(attention.textContent).toContain("Degradation detected");
    expect(attention.textContent).toContain("Mobile app: 72.0% success against a 90.8% baseline (−18.8 pts)");
    expect(attention.textContent).toContain("52 failed of 186 completed attempts");
    const review = hrefOf(el, "Review unresolved mobile app payments");
    expect(review.pathname).toBe("/payments");
    expect(review.searchParams.get("status")).toBe("failed");
    expect(review.searchParams.get("channel")).toBe("mobile_app");
    expect(review.searchParams.get("period")).toBe("last_7_days");
    expect(review.searchParams.get("return_to")).toBe("/payment-health?period=last_7_days");
  });

  it("shows completed-attempt metrics against the baseline and says pending attempts are not counted", async () => {
    mockFetch(handlerFor(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(el.querySelector("[aria-label='Success rate']")?.textContent).toContain("84.7%");
    expect(el.querySelector("[aria-label='Success rate']")?.textContent).toContain("Baseline 91.0% · −6.3 pts");
    expect(el.querySelector("[aria-label='Completed attempts']")?.textContent).toContain("499 succeeded · 90 failed");
    expect(el.querySelector("[aria-label='Pending attempts']")?.textContent).toContain("Not counted in the rate");
    const failed = hrefOf(el, "View failed attempts");
    expect(failed.searchParams.get("tab")).toBe("attempts");
    expect(failed.searchParams.get("outcome")).toBe("failed");
  });

  it("charts the daily rate with a gap, a low-volume marker and counts in the tooltip", async () => {
    mockFetch(handlerFor(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(el.querySelectorAll("polyline.chart-line").length).toBe(2);
    expect(el.querySelectorAll("circle.chart-point-low").length).toBe(1);
    const tips = Array.from(el.querySelectorAll(".chart-day > title")).map((t) => t.textContent);
    expect(tips[0]).toBe("Sep 29: 95.0% (76 of 80 completed attempts succeeded, 4 failed)");
    expect(tips[1]).toBe("Sep 30: no completed attempts");
    expect(tips[2]).toContain("low volume");
  });

  it("scopes the page to a channel when its row is selected, and back to all channels", async () => {
    const { calls } = mockFetch(handlerFor(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=month_to_date");
    await flush();
    const button = Array.from(page.container.querySelectorAll("button.link-button")).find((b) => b.textContent === "Mobile app")!;
    expect(button.getAttribute("aria-pressed")).toBe("false");
    await click(button);
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=month_to_date&channel=mobile_app");
    await setValue(page.container.querySelector("#health-channel"), "");
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=month_to_date");
  });

  it("lists recorded failure signals, each linking to the matching failed attempts", async () => {
    mockFetch(handlerFor(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=custom&from=2026-09-29&to=2026-10-05&channel=mobile_app");
    await flush();
    const el = page.container;
    expect(el.textContent).toContain("Recorded failure signals");
    expect(el.textContent).toContain("not confirmed root causes");
    const link = el.querySelector("a[aria-label='31 failed attempts recorded as Issuer unavailable']")!;
    const url = new URL(link.getAttribute("href")!, "http://x");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      tab: "attempts",
      period: "custom",
      from: "2026-09-29",
      to: "2026-10-05",
      channel: "mobile_app",
      outcome: "failed",
      failure_code: "issuer_unavailable",
      return_to: "/payment-health?period=custom&from=2026-09-29&to=2026-10-05&channel=mobile_app",
    });
  });

  it("shows recovery per payment as payment amounts, and the first unresolved payments with a link to all of them", async () => {
    const { calls } = mockFetch(handlerFor(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    const recovery = el.querySelector(".health-recovery")!;
    expect(recovery.textContent).toContain("71 payments · $21,045.12");
    expect(recovery.textContent).toContain("50 within 1 hour of the first attempt");
    expect(recovery.textContent).toContain("21 payments · $7,244.68");
    expect(recovery.textContent).not.toMatch(/revenue/i);
    const unresolvedCall = calls.find((c) => c.url.startsWith("/api/payments?"));
    expect(unresolvedCall?.url).toBe("/api/payments?period=last_7_days&status=failed&sort=created_at&dir=desc&page_size=10");
    expect(recovery.querySelectorAll("tbody tr").length).toBe(PAYMENTS.items.length);
    const all = hrefOf(el, "Review all 21 in Payments");
    expect(all.searchParams.get("status")).toBe("failed");
    expect(all.searchParams.get("return_to")).toBe("/payment-health?period=last_7_days");
  });

  it("says plainly when no significant degradation is detected and which channels were not assessed", async () => {
    mockFetch(handlerFor(QUIET));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const attention = page.container.querySelector(".health-attention")!;
    expect(attention.textContent).toContain("No significant degradation detected");
    expect(attention.textContent).toContain("10.0 pts or more below its baseline");
    expect(attention.textContent).toContain("Not assessed for lack of volume: In store.");
    expect(page.container.textContent).toContain("Not enough volume to assess");
  });

  it("shows an empty state instead of a rate when nothing completed, with the pending count", async () => {
    mockFetch(handlerFor(EMPTY));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(el.textContent).toContain("No completed attempts in this period");
    expect(el.textContent).toContain("2 attempts are still pending, so there is no success rate to show.");
    expect(el.querySelector("[aria-label='Success rate']")).toBeNull();
    expect(el.textContent).not.toContain("%");
    expect(el.textContent).toContain("Every affected payment has recovered or is still being retried.");
  });

  it("defines every term in the product", async () => {
    mockFetch(handlerFor(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const terms = Array.from(page.container.querySelectorAll(".health-definitions dt")).map((d) => d.textContent);
    expect(terms).toEqual(["Success rate", "Baseline", "Degraded", "Affected", "Recovered", "Unresolved", "Retry in progress", "Recorded failure signal"]);
    expect(page.container.querySelector(".health-definitions")?.textContent).toContain("10.0 pts or more below its baseline, when the period has at least 50 completed attempts and the baseline at least 100");
  });

  it("shows the forbidden state on 403", async () => {
    mockFetch(handlerFor({ status: 403, body: { error: { code: "forbidden", message: "Your role does not include payments:read." } } }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.textContent).toContain("Your role does not include this section");
  });
});
