import { afterEach, describe, expect, it } from "vitest";
import type { ChannelHealth, PaymentHealth } from "../../api/payment-health-types";
import { META, PAYMENTS, PERIOD } from "../../test/fixtures";
import { MAYA, mockFetch, type Handler } from "../../test/mockApi";
import { click, flush, renderPage, setValue, type Rendered } from "../../test/render";
import { safeHealthBack } from "./links";
import { PaymentHealthPage } from "./PaymentHealthPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

function channel(overrides: Partial<ChannelHealth> & Pick<ChannelHealth, "channel" | "channel_label">): ChannelHealth {
  return {
    succeeded: 245,
    failed: 21,
    pending: 1,
    completed: 266,
    success_rate_bp: 9211,
    baseline_succeeded: 969,
    baseline_failed: 91,
    baseline_completed: 1060,
    baseline_rate_bp: 9142,
    change_bp: 69,
    assessment: "within_baseline",
    assessment_label: "Within baseline",
    ...overrides,
  };
}

const DEGRADED: PaymentHealth = {
  as_of: "2026-10-05T14:12:00Z",
  period: PERIOD,
  baseline: { from_date: "2026-08-30", to_date: "2026-09-28", range_label: "Aug 30 – Sep 28, 2026" },
  channel: null,
  channel_label: null,
  thresholds: { degraded_drop_bp: 500, min_period_completed: 50, min_baseline_completed: 200, low_volume_day_completed: 10, baseline_days: 30, quick_recovery_seconds: 3600 },
  summary: {
    succeeded: 499, failed: 90, pending: 2, completed: 589, success_rate_bp: 8472,
    baseline_succeeded: 1903, baseline_failed: 182, baseline_completed: 2085, baseline_rate_bp: 9127, change_bp: -655,
  },
  channels: [
    channel({ channel: "website", channel_label: "Website" }),
    channel({
      channel: "mobile_app", channel_label: "Mobile app", succeeded: 134, failed: 52, pending: 1, completed: 186, success_rate_bp: 7204,
      baseline_succeeded: 572, baseline_failed: 58, baseline_completed: 630, baseline_rate_bp: 9079, change_bp: -1875, assessment: "degraded", assessment_label: "Degraded",
    }),
    channel({ channel: "in_store", channel_label: "In store", completed: 37, succeeded: 35, failed: 2, pending: 0, assessment: "insufficient_period_volume", assessment_label: "Not enough completed attempts" }),
  ],
  trend: [
    { day: "2026-09-29", succeeded: 75, failed: 4, pending: 0, completed: 79, success_rate_bp: 9494, low_volume: false },
    { day: "2026-09-30", succeeded: 0, failed: 0, pending: 0, completed: 0, success_rate_bp: null, low_volume: false },
    { day: "2026-10-01", succeeded: 84, failed: 38, pending: 0, completed: 122, success_rate_bp: 6885, low_volume: false },
    { day: "2026-10-05", succeeded: 6, failed: 1, pending: 2, completed: 7, success_rate_bp: 8571, low_volume: true },
  ],
  failure_signals: [
    { code: "issuer_unavailable", label: "Issuer unavailable", failed_attempts: 32, share_bp: 3556 },
    { code: "do_not_honor", label: "Do not honor", failed_attempts: 58, share_bp: 6444 },
  ],
  recovery: {
    affected: { payments: 83, amount_cents: 2334007 },
    recovered: { payments: 55, amount_cents: 1571734 },
    recovered_within_hour: { payments: 50, amount_cents: 1400000 },
    unresolved: { payments: 28, amount_cents: 762273 },
    awaiting_retry: { payments: 0, amount_cents: 0 },
    currency: "USD",
  },
};

const HEALTHY: PaymentHealth = {
  ...DEGRADED,
  channels: DEGRADED.channels.map((c) => (c.assessment === "degraded" ? { ...c, assessment: "within_baseline", assessment_label: "Within baseline", change_bp: -100 } : c)),
};

const EMPTY: PaymentHealth = {
  ...DEGRADED,
  summary: { ...DEGRADED.summary, succeeded: 0, failed: 0, pending: 0, completed: 0, success_rate_bp: null, change_bp: null },
  channels: DEGRADED.channels.map((c) => ({ ...c, succeeded: 0, failed: 0, pending: 0, completed: 0, success_rate_bp: null, change_bp: null, assessment: "no_completed_attempts", assessment_label: "No completed attempts" })),
  trend: DEGRADED.trend.map((t) => ({ ...t, succeeded: 0, failed: 0, pending: 0, completed: 0, success_rate_bp: null, low_volume: false })),
  failure_signals: [],
  recovery: { ...DEGRADED.recovery, affected: { payments: 0, amount_cents: 0 }, recovered: { payments: 0, amount_cents: 0 }, recovered_within_hour: { payments: 0, amount_cents: 0 }, unresolved: { payments: 0, amount_cents: 0 } },
};

function handlerFor(health: PaymentHealth | { status: number; body: unknown }): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: MAYA };
    if (url === "/api/meta") return { status: 200, body: META };
    if (url.startsWith("/api/payment-health")) return "status" in health && "body" in health ? health : { status: 200, body: health };
    if (url.startsWith("/api/payments?")) return { status: 200, body: { ...PAYMENTS, items: PAYMENTS.items.slice(0, 1), total: 28 } };
    return undefined;
  };
}

function links(el: HTMLElement): string[] {
  return Array.from(el.querySelectorAll("a")).map((a) => a.getAttribute("href") ?? "");
}

describe("PaymentHealthPage", () => {
  it("requests the period and channel from the URL", async () => {
    const { calls } = mockFetch(handlerFor(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=month_to_date&channel=mobile_app");
    await flush();
    const call = calls.find((c) => c.url.startsWith("/api/payment-health"));
    expect(call?.url).toBe("/api/payment-health?period=month_to_date&channel=mobile_app");
    const unresolved = calls.find((c) => c.url.startsWith("/api/payments?"));
    expect(unresolved?.url).toContain("channel=mobile_app");
    expect(unresolved?.url).toContain("status=failed");
    expect(unresolved?.url).toContain("page_size=5");
  });

  it("names a degraded channel with its rate, baseline and failed attempts, and links to the evidence", async () => {
    mockFetch(handlerFor(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const attention = page.container.querySelector(".health-attention") as HTMLElement;
    expect(attention.textContent).toContain("Mobile app is degraded");
    expect(attention.textContent).toContain("72.0% success vs a 90.8% baseline (−18.8 pts)");
    expect(attention.textContent).toContain("52 failed of 186 completed attempts");
    expect(attention.textContent).not.toContain("No significant degradation");
    const back = encodeURIComponent("/payment-health?period=last_7_days");
    expect(links(attention)).toContain(`/payments?tab=attempts&period=last_7_days&channel=mobile_app&outcome=failed&back=${back}`);
    expect(links(attention)).toContain(`/payments?period=last_7_days&channel=mobile_app&status=failed&back=${back}`);
    // Low volume is said plainly, never turned into a verdict.
    expect(attention.textContent).toContain("In store not assessed");
    expect(attention.textContent).toContain("37 in this period, 50 needed");
  });

  it("says plainly when no significant degradation is detected", async () => {
    mockFetch(handlerFor(HEALTHY));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.querySelector(".health-attention")?.textContent).toContain("No significant degradation detected.");
    expect(page.container.querySelector(".health-attention")?.textContent).toContain("5.0 pts or more");
  });

  it("shows tiles with pending attempts excluded, a trend with gaps and low-volume days, and payment values", async () => {
    mockFetch(handlerFor(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(el.querySelector("[aria-label='Success rate'] .stat-value")?.textContent).toBe("84.7%");
    expect(el.querySelector("[aria-label='Success rate'] .stat-foot")?.textContent).toBe("Baseline 91.3% · −6.6 pts");
    expect(el.querySelector("[aria-label='Pending attempts']")?.textContent).toContain("excluded from the success rate");
    expect(el.querySelectorAll("path.chart-line").length).toBe(2);
    expect(el.querySelectorAll(".chart-point-low").length).toBe(1);
    expect(el.querySelector("svg desc")?.textContent).toContain("Sep 30: No completed attempts.");
    expect(el.querySelector("svg desc")?.textContent).toContain("Oct 1: 68.9% · 84 succeeded, 38 failed, 0 pending.");
    expect(el.textContent).toContain("Recovered within 1 hour of the first attempt");
    expect(el.textContent).toContain("$23,340.07");
    expect(el.textContent?.toLowerCase()).not.toContain("lost revenue");
  });

  it("links each recorded failure signal to the matching failed attempts and calls them signals, not causes", async () => {
    mockFetch(handlerFor(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=last_7_days&channel=mobile_app");
    await flush();
    const el = page.container;
    expect(el.textContent).toContain("not confirmed root causes");
    const back = encodeURIComponent("/payment-health?period=last_7_days&channel=mobile_app");
    expect(links(el)).toContain(`/payments?tab=attempts&period=last_7_days&channel=mobile_app&outcome=failed&failure_code=issuer_unavailable&back=${back}`);
    expect(el.textContent).toContain("Review all 28 in Payments");
  });

  it("scopes the page to a channel when its row is selected, and clears it when selected again", async () => {
    const { calls } = mockFetch(handlerFor(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const button = Array.from(page.container.querySelectorAll("button.link-button")).find((b) => b.textContent === "Mobile app");
    expect(button?.getAttribute("aria-pressed")).toBe("false");
    await click(button ?? null);
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=last_7_days&channel=mobile_app");
    await setValue(page.container.querySelector("#health-channel"), "");
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=last_7_days");
  });

  it("marks the selected channel row", async () => {
    mockFetch(handlerFor({ ...DEGRADED, channel: "mobile_app", channel_label: "Mobile app" }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?channel=mobile_app");
    await flush();
    const selected = page.container.querySelector("tr.row-selected");
    expect(selected?.textContent).toContain("Mobile app");
    expect(selected?.querySelector("button")?.getAttribute("aria-pressed")).toBe("true");
  });

  it("shows an empty state instead of a fabricated rate when nothing completed", async () => {
    mockFetch(handlerFor(EMPTY));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?from=2026-08-01&to=2026-08-07");
    await flush();
    const el = page.container;
    expect(el.querySelector("[aria-label='Success rate'] .stat-value")?.textContent).toBe("—");
    expect(el.textContent).toContain("No completed attempts in this period");
    expect(el.querySelector("svg[role=img]")).toBeNull();
    expect(el.textContent).toContain("No failed attempts recorded");
    expect(el.textContent).toContain("No payments created in this period had a failed attempt.");
    expect(el.querySelector(".health-attention")?.textContent).not.toContain("No significant degradation");
  });

  it("shows the error state when the request fails, and the 403 state when the backend refuses", async () => {
    mockFetch(handlerFor({ status: 500, body: { error: { code: "internal", message: "boom" } } }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.querySelector(".state-error")?.textContent).toContain("Could not load this view");
    page.unmount();
    mockFetch(handlerFor({ status: 403, body: { error: { code: "forbidden", message: "no" } } }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.querySelector(".state-forbidden")).not.toBeNull();
    expect(page.container.querySelector(".health-attention")).toBeNull();
  });
});

describe("safeHealthBack", () => {
  it("accepts only Payment Health paths", () => {
    expect(safeHealthBack("/payment-health?period=last_7_days")).toBe("/payment-health?period=last_7_days");
    expect(safeHealthBack("/payment-health")).toBe("/payment-health");
    expect(safeHealthBack("https://example.com/payment-health")).toBeNull();
    expect(safeHealthBack("//evil.example.com")).toBeNull();
    expect(safeHealthBack("/payment-healthy")).toBeNull();
    expect(safeHealthBack("")).toBeNull();
  });
});
