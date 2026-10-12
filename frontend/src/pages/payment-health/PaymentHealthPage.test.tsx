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

const stats = (succeeded: number, failed: number, pending: number, rate: number | null) => ({ succeeded, failed, pending, completed: succeeded + failed, success_rate_bps: rate });

const CHANNELS: ChannelHealth[] = [
  { channel: "website", label: "Website", period: stats(246, 20, 1, 9248), baseline: stats(969, 91, 0, 9142), delta_bps: 106, assessment: "normal", assessment_label: "No significant degradation" },
  { channel: "mobile_app", label: "Mobile app", period: stats(134, 52, 1, 7204), baseline: stats(572, 58, 0, 9079), delta_bps: -1875, assessment: "degraded", assessment_label: "Degraded" },
  { channel: "in_store", label: "In store", period: stats(20, 2, 0, 9091), baseline: stats(362, 33, 0, 9165), delta_bps: -74, assessment: "insufficient_data", assessment_label: "Not enough data" },
];

const HEALTH: PaymentHealth = {
  period: PERIOD,
  baseline: { from_date: "2026-08-30", to_date: "2026-09-28", range_label: "Aug 30 – Sep 28, 2026" },
  channel: null,
  channel_label: null,
  rules: {
    baseline_days: 30,
    degraded_drop_bps: 1000,
    min_period_completed: 30,
    min_baseline_completed: 100,
    low_volume_day_completed: 10,
    recovery_window_seconds: 3600,
  },
  summary: { period: stats(400, 74, 2, 8439), baseline: stats(1903, 182, 0, 9127), delta_bps: -688 },
  channels: CHANNELS,
  trend: [
    { day: "2026-09-29", ...stats(60, 4, 0, 9375), low_volume: false },
    { day: "2026-09-30", ...stats(0, 0, 0, null), low_volume: true },
    { day: "2026-10-01", ...stats(40, 30, 0, 5714), low_volume: false },
    { day: "2026-10-02", ...stats(5, 3, 0, 6250), low_volume: true },
    { day: "2026-10-03", ...stats(120, 10, 0, 9231), low_volume: false },
    { day: "2026-10-04", ...stats(150, 20, 0, 8824), low_volume: false },
    { day: "2026-10-05", ...stats(25, 7, 2, 7813), low_volume: false },
  ],
  failure_signals: [
    { failure_code: "issuer_unavailable", label: "Issuer unavailable", failed_attempts: 40 },
    { failure_code: "insufficient_funds", label: "Insufficient funds", failed_attempts: 34 },
  ],
  recovery: {
    affected_payments: 60,
    affected_cents: 1234567,
    recovered_payments: 48,
    recovered_cents: 1000000,
    recovered_within_window_payments: 45,
    recovered_within_window_cents: 900000,
    unresolved_payments: 12,
    unresolved_cents: 234567,
    retry_pending_payments: 0,
    retry_pending_cents: 0,
    currency: "USD",
  },
  unresolved_payments: { items: PAYMENTS.items, total: 12 },
};

function handlerFor(health: (url: string) => PaymentHealth | { status: number; body: unknown }): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: MAYA };
    if (url === "/api/meta") return { status: 200, body: META };
    if (url.startsWith("/api/payment-health")) {
      const result = health(url);
      return "status" in result && "body" in result ? result : { status: 200, body: result };
    }
    return undefined;
  };
}

function link(el: HTMLElement, text: string): HTMLAnchorElement {
  const found = Array.from(el.querySelectorAll("a")).find((a) => a.textContent?.includes(text) || a.getAttribute("aria-label")?.includes(text));
  if (!found) throw new Error(`no link ${text}`);
  return found;
}

function params(href: string): URLSearchParams {
  return new URLSearchParams(href.split("?")[1] ?? "");
}

describe("PaymentHealthPage", () => {
  it("requests the default scope and names the degraded channel with its evidence", async () => {
    const { calls } = mockFetch(handlerFor(() => HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(calls.find((c) => c.url.startsWith("/api/payment-health"))?.url).toBe("/api/payment-health?period=last_7_days");
    const attention = el.querySelector(".health-attention")!;
    expect(attention.querySelector("h2")?.textContent).toBe("Mobile app is degraded");
    expect(attention.textContent).toContain("72.0% success against a baseline of 90.8% (−18.8 pts), 52 failed attempts.");
    expect(attention.textContent).toContain("In store: 22 completed attempts in this period and 395 in the baseline; at least 30 and 100 are needed.");
    expect(attention.textContent).not.toContain("No significant degradation detected");

    const unresolved = params(link(el, "Review unresolved mobile app payments").getAttribute("href")!);
    expect(unresolved.get("status")).toBe("failed");
    expect(unresolved.get("channel")).toBe("mobile_app");
    expect(unresolved.get("period")).toBe("last_7_days");
    expect(unresolved.get("health")).toBe("period=last_7_days");
    const failed = params(link(attention as HTMLElement, "View failed attempts").getAttribute("href")!);
    expect(failed.get("tab")).toBe("attempts");
    expect(failed.get("outcome")).toBe("failed");
    expect(failed.get("channel")).toBe("mobile_app");
  });

  it("shows completed-attempt tiles with pending counted separately and the baseline beside the rate", async () => {
    mockFetch(handlerFor(() => HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const tile = (label: string) => page!.container.querySelector(`[aria-label="${label}"]`)?.textContent ?? "";
    expect(tile("Success rate")).toContain("84.4%");
    expect(tile("Success rate")).toContain("Baseline 91.3% · −6.9 pts");
    expect(tile("Success rate")).toContain("400 of 474 completed attempts succeeded");
    expect(tile("Failed attempts")).toContain("74");
    expect(tile("Pending attempts")).toContain("2");
    expect(tile("Pending attempts")).toContain("not counted in the success rate");
    expect(tile("Affected payments")).toContain("$12,345.67 in payment amounts");
    expect(tile("Recovered payments")).toContain("45 within 1 hour of the first attempt");
    expect(tile("Unresolved payments")).toContain("$2,345.67");
    expect(page.container.textContent).not.toMatch(/lost revenue|revenue lost/i);
  });

  it("draws the trend with a gap, low-volume markers and a baseline", async () => {
    mockFetch(handlerFor(() => HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const chart = page.container.querySelector("svg.rate-chart")!;
    expect(chart.querySelectorAll("path.chart-line").length).toBe(2);
    expect(chart.querySelectorAll(".chart-gap").length).toBe(1);
    expect(chart.querySelectorAll(".chart-point-low").length).toBe(1);
    expect(chart.querySelector(".chart-baseline title")?.textContent).toBe("Baseline, Aug 30 – Sep 28, 2026: 91.3%");
    const titles = Array.from(chart.querySelectorAll(".chart-point title, .chart-gap title")).map((t) => t.textContent);
    expect(titles[1]).toBe("Sep 30: no completed attempts · 0 succeeded, 0 failed, 0 pending");
    expect(titles[2]).toBe("Oct 1: 57.1% · 40 succeeded, 30 failed, 0 pending");
    expect(titles[3]).toBe("Oct 2: 62.5% (low volume) · 5 succeeded, 3 failed, 0 pending");
  });

  it("scopes the page to a channel from its row and back to all channels", async () => {
    const { calls } = mockFetch(handlerFor((url) => (url.includes("channel=mobile_app") ? { ...HEALTH, channel: "mobile_app", channel_label: "Mobile app" } : HEALTH)));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=month_to_date");
    await flush();
    await click(link(page.container, "Scope the page to Mobile app"));
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=month_to_date&channel=mobile_app");
    expect(link(page.container, "Scope the page to Mobile app").getAttribute("aria-current")).toBe("true");
    expect(link(page.container, "Scope the page to Website").getAttribute("aria-current")).toBeNull();
    expect(page.container.textContent).toContain("Mobile app · Sep 29 – Oct 5, 2026");

    // Every drill-down now carries the channel and a way back to this exact scope.
    const signal = params(link(page.container, "recorded as Issuer unavailable").getAttribute("href")!);
    expect(signal.get("failure_code")).toBe("issuer_unavailable");
    expect(signal.get("outcome")).toBe("failed");
    expect(signal.get("channel")).toBe("mobile_app");
    expect(signal.get("health")).toBe("period=month_to_date&channel=mobile_app");

    await click(link(page.container, "Show all channels"));
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=month_to_date");
  });

  it("changes channel from the filter", async () => {
    const { calls } = mockFetch(handlerFor(() => HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    await setValue(page.container.querySelector("#health-channel"), "in_store");
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=last_7_days&channel=in_store");
  });

  it("says plainly when nothing is degraded", async () => {
    const healthy = CHANNELS.map((c) => ({ ...c, assessment: "normal" as const, assessment_label: "No significant degradation" }));
    mockFetch(handlerFor(() => ({ ...HEALTH, channels: healthy })));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const attention = page.container.querySelector(".health-attention")!;
    expect(attention.querySelector("h2")?.textContent).toBe("No significant degradation detected");
    expect(attention.textContent).toContain("None of Website, Mobile app and In store fell 10.0 pts or more below their own baseline.");
  });

  it("draws no conclusion when no channel has enough data", async () => {
    const thin = CHANNELS.map((c) => ({ ...c, assessment: "insufficient_data" as const, assessment_label: "Not enough data" }));
    mockFetch(handlerFor(() => ({ ...HEALTH, channels: thin })));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=last_30_days");
    await flush();
    const attention = page.container.querySelector(".health-attention")!;
    expect(attention.querySelector("h2")?.textContent).toBe("Not enough data to assess channel health");
    expect(attention.textContent).not.toContain("No significant degradation detected");
    expect(attention.querySelectorAll(".health-not-evaluated li").length).toBe(3);
  });

  it("shows an empty state instead of a rate when nothing completed", async () => {
    const pendingOnly: PaymentHealth = {
      ...HEALTH,
      channel: "website",
      channel_label: "Website",
      summary: { period: stats(0, 0, 2, null), baseline: stats(19, 4, 0, 8261), delta_bps: null },
      trend: [{ day: "2026-10-05", ...stats(0, 0, 2, null), low_volume: true }],
      failure_signals: [],
      recovery: { ...HEALTH.recovery, affected_payments: 0, affected_cents: 0, recovered_payments: 0, recovered_cents: 0, recovered_within_window_payments: 0, recovered_within_window_cents: 0, unresolved_payments: 0, unresolved_cents: 0 },
      unresolved_payments: { items: [], total: 0 },
    };
    mockFetch(handlerFor(() => pendingOnly));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=custom&from=2026-10-05&to=2026-10-05&channel=website");
    await flush();
    const el = page.container;
    expect(el.textContent).toContain("No completed attempts in this scope");
    expect(el.textContent).toContain("2 pending attempts are still waiting for an outcome");
    expect(el.querySelector('[aria-label="Success rate"]')).toBeNull();
    expect(el.querySelector("svg.rate-chart")).toBeNull();
    expect(el.textContent).toContain("No failed attempts recorded");
    expect(el.textContent).toContain("No affected payments");
    expect(el.textContent).toContain("No unresolved payments");
  });

  it("documents every definition with the thresholds the API applies", async () => {
    mockFetch(handlerFor(() => HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const definitions = page.container.querySelector(".health-definitions")!;
    const terms = Array.from(definitions.querySelectorAll("dt")).map((dt) => dt.textContent);
    expect(terms).toEqual(expect.arrayContaining(["Success rate", "Baseline", "Degraded", "Affected payment", "Recovered", "Unresolved", "Recorded failure signal"]));
    expect(definitions.textContent).toContain("10.0 pts or more below its own baseline");
    expect(definitions.textContent).toContain("at least 30 completed attempts in the period and 100 in the baseline");
    expect(definitions.textContent).toContain("not a confirmed root cause");
  });

  it("links to every unresolved payment in Payments", async () => {
    mockFetch(handlerFor(() => HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=last_7_days&channel=mobile_app");
    await flush();
    const all = params(link(page.container, "Review all 12 in Payments").getAttribute("href")!);
    expect(all.get("status")).toBe("failed");
    expect(all.get("channel")).toBe("mobile_app");
    expect(all.get("health")).toBe("period=last_7_days&channel=mobile_app");
    expect(page.container.textContent).toContain("Showing the 2 most recent of 12.");
  });

  it("shows the forbidden state when the API refuses", async () => {
    mockFetch(handlerFor(() => ({ status: 403, body: { error: { code: "forbidden", message: "Your role does not include this section." } } })));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.textContent).toContain("Your role does not include this section");
  });
});
