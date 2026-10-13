import { afterEach, describe, expect, it } from "vitest";
import type { ChannelHealth, OutcomeCounts, PaymentHealth } from "../../api/payment-health-types";
import { META } from "../../test/fixtures";
import { MAYA, mockFetch, type Handler } from "../../test/mockApi";
import { click, flush, renderPage, type Rendered } from "../../test/render";
import { PaymentHealthPage } from "./PaymentHealthPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

function counts(succeeded: number, failed: number, pending = 0): OutcomeCounts {
  const completed = succeeded + failed;
  return { succeeded, failed, pending, completed, success_rate_bps: completed ? Math.round((succeeded * 10000) / completed) : null };
}

function channel(name: string, label: string, period: OutcomeCounts, baseline: OutcomeCounts, evaluation: ChannelHealth["evaluation"], evaluationLabel: string): ChannelHealth {
  const drop = period.success_rate_bps !== null && baseline.success_rate_bps !== null ? baseline.success_rate_bps - period.success_rate_bps : null;
  return { channel: name, channel_label: label, period, baseline, drop_bps: drop, evaluation, evaluation_label: evaluationLabel };
}

const MOBILE = channel("mobile_app", "Mobile app", counts(134, 52, 1), counts(572, 58), "degraded", "Degraded");
const WEBSITE = channel("website", "Website", counts(246, 20, 1), counts(969, 91), "not_degraded", "No significant degradation");

const HEALTH: PaymentHealth = {
  period: { preset: "last_7_days", label: "Last 7 days", from_date: "2026-09-29", to_date: "2026-10-05", range_label: "Sep 29 – Oct 5, 2026" },
  baseline_period: { from_date: "2026-08-30", to_date: "2026-09-28", range_label: "Aug 30 – Sep 28, 2026" },
  channel: null,
  channel_label: "All channels",
  thresholds: { baseline_days: 30, min_period_completed: 50, min_baseline_completed: 100, degraded_drop_bps: 1000, low_volume_day_completed: 10, recovery_window_minutes: 60 },
  summary: { period: counts(380, 72, 2), baseline: counts(1541, 149) },
  attention: { status: "degraded", status_label: "Degraded", degraded: [MOBILE], not_evaluated: [] },
  channels: [WEBSITE, MOBILE],
  daily: [
    { day: "2026-09-29", succeeded: 60, failed: 5, pending: 0, success_rate_bps: 9231, low_volume: false },
    { day: "2026-09-30", succeeded: 0, failed: 0, pending: 0, success_rate_bps: null, low_volume: false },
    { day: "2026-10-01", succeeded: 4, failed: 3, pending: 0, success_rate_bps: 5714, low_volume: true },
  ],
  failure_signals: [
    { code: "issuer_unavailable", label: "Issuer unavailable", failed_attempts: 32 },
    { code: "do_not_honor", label: "Do not honor", failed_attempts: 17 },
  ],
  recovery: {
    affected_payments: 83,
    recovered_payments: 55,
    recovered_within_window: 54,
    unresolved_payments: 28,
    unresolved_retry_pending: 1,
    affected_cents: 2334007,
    recovered_cents: 1571734,
    unresolved_cents: 762273,
    currency: "USD",
  },
  unresolved: [
    {
      id: "pay_unresolved0001",
      order_reference: "AL-12001",
      created_at: "2026-10-01T21:10:00Z",
      amount_cents: 18450,
      currency: "USD",
      channel: "mobile_app",
      channel_label: "Mobile app",
      status: "failed",
      status_label: "Failed",
      failed_attempts: 2,
      last_failure_code: "issuer_unavailable",
      last_failure_label: "Issuer unavailable",
      customer: { id: "cus_taylorreed0001", full_name: "Taylor Reed", email: "taylor.reed@example.com", reference: "C-1001" },
    },
  ],
};

function handlerWith(body: PaymentHealth | ((url: string) => PaymentHealth)): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: MAYA };
    if (url === "/api/meta") return { status: 200, body: META };
    if (url.startsWith("/api/payment-health")) return { status: 200, body: typeof body === "function" ? body(url) : body };
    return undefined;
  };
}

function linkByText(el: Element, text: string): HTMLAnchorElement | undefined {
  return Array.from(el.querySelectorAll("a")).find((a) => a.textContent?.includes(text));
}

describe("PaymentHealthPage", () => {
  it("names the degraded channel with its evidence and links to its unresolved payments", async () => {
    const { calls } = mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(calls.find((c) => c.url.startsWith("/api/payment-health"))?.url).toBe("/api/payment-health?period=last_7_days");
    const attention = el.querySelector(".health-attention");
    expect(attention?.textContent).toContain("Degraded: Mobile app");
    expect(attention?.textContent).toContain("72.0% success against a 90.8% baseline, 18.8 pp below; 52 failed attempts");
    expect(attention?.textContent).toContain("2 attempts are still pending; they are not counted in any success rate.");
    expect(linkByText(el, "Review unresolved mobile app payments")?.getAttribute("href")).toBe(
      "/payments?period=last_7_days&channel=mobile_app&recovery=unresolved&health=period%3Dlast_7_days%26channel%3Dmobile_app",
    );
    expect(el.textContent).toContain("84.1%");
    expect(el.textContent).toContain("380 of 452 completed attempts succeeded");
    expect(el.textContent).toContain("$7,622.73 payment value");
    expect(el.textContent).toContain("54 within 60 minutes of the first attempt");
    expect(el.textContent).toContain("Review all 28 in Payments");
    expect(el.textContent?.toLowerCase()).not.toContain("lost revenue");
  });

  it("draws gaps for days without completed attempts, marks low-volume days and shows the baseline", async () => {
    mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const svg = page.container.querySelector("svg.rate-chart");
    expect(svg).not.toBeNull();
    const points = svg!.querySelectorAll("circle.rate-point");
    expect(points.length).toBe(2);
    expect(points[0]?.getAttribute("tabindex")).toBe("0");
    expect(points[0]?.querySelector("title")?.textContent).toBe("Sep 29: 92.3% (60 succeeded, 5 failed, 0 pending)");
    expect(svg!.querySelectorAll("circle.rate-point-low").length).toBe(1);
    expect(svg!.querySelector("circle.rate-point-low title")?.textContent).toContain("low volume");
    expect(svg!.querySelectorAll("polyline.rate-line").length).toBe(2);
    expect(svg!.querySelector(".rate-gap title")?.textContent).toBe("Sep 30: no completed attempts (0 succeeded, 0 failed, 0 pending)");
    expect(svg!.querySelector("line.rate-baseline")).not.toBeNull();
    expect(svg!.querySelector("desc")?.textContent).toContain("Baseline 91.2%.");
  });

  it("scopes the page to a channel from the table and keeps it in the URL", async () => {
    const { calls } = mockFetch(handlerWith((url) => (url.includes("channel=mobile_app") ? { ...HEALTH, channel: "mobile_app", channel_label: "Mobile app" } : HEALTH)));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=month_to_date");
    await flush();
    const button = Array.from(page.container.querySelectorAll<HTMLButtonElement>("button.link-button")).find((b) => b.textContent === "Mobile app");
    expect(button?.getAttribute("aria-pressed")).toBe("false");
    await click(button ?? null);
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=month_to_date&channel=mobile_app");
    const selected = Array.from(page.container.querySelectorAll<HTMLButtonElement>("button.link-button")).find((b) => b.textContent === "Mobile app");
    expect(selected?.getAttribute("aria-pressed")).toBe("true");
    expect(selected?.closest("tr")?.classList.contains("row-selected")).toBe(true);
    expect(page.container.textContent).toContain("Show all channels");
  });

  it("links each recorded failure signal to the matching failed attempts", async () => {
    mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=custom&from=2026-10-01&to=2026-10-02");
    await flush();
    const el = page.container;
    expect(el.textContent).toContain("not confirmed root causes");
    expect(linkByText(el, "Issuer unavailable")?.getAttribute("href")).toBe(
      "/payments?period=custom&from=2026-10-01&to=2026-10-02&tab=attempts&outcome=failed&failure_code=issuer_unavailable&health=period%3Dcustom%26from%3D2026-10-01%26to%3D2026-10-02",
    );
  });

  it("says plainly when nothing is degraded and when volume is too low", async () => {
    mockFetch(handlerWith({ ...HEALTH, attention: { status: "not_degraded", status_label: "No significant degradation", degraded: [], not_evaluated: [] } }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.querySelector(".health-attention")?.textContent).toContain("No significant degradation detected");
    page.unmount();

    const thin = channel("website", "Website", counts(3, 1), counts(20, 3), "insufficient_volume", "Not enough volume to evaluate");
    mockFetch(handlerWith({ ...HEALTH, attention: { status: "insufficient_volume", status_label: "Not enough volume to evaluate", degraded: [], not_evaluated: [thin] } }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const text = page.container.querySelector(".health-attention")?.textContent ?? "";
    expect(text).toContain("Not enough volume to evaluate");
    expect(text).toContain("at least 50 completed attempts in the period and 100 in its baseline");
    expect(text).toContain("Website (4 completed in the period, 23 in the baseline)");
  });

  it("shows an empty state, not a success rate, when nothing was attempted", async () => {
    const empty: PaymentHealth = {
      ...HEALTH,
      summary: { period: counts(0, 0), baseline: counts(0, 0) },
      attention: { status: "no_completed", status_label: "No completed attempts", degraded: [], not_evaluated: [] },
      channels: [],
      daily: [{ day: "2026-08-01", succeeded: 0, failed: 0, pending: 0, success_rate_bps: null, low_volume: false }],
      failure_signals: [],
      recovery: { ...HEALTH.recovery, affected_payments: 0, recovered_payments: 0, recovered_within_window: 0, unresolved_payments: 0, unresolved_retry_pending: 0, affected_cents: 0, recovered_cents: 0, unresolved_cents: 0 },
      unresolved: [],
    };
    mockFetch(handlerWith(empty));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?from=2026-08-01&to=2026-08-01");
    await flush();
    const el = page.container;
    expect(el.textContent).toContain("No payment attempts in this period");
    expect(el.querySelector("[aria-label='Success rate']")).toBeNull();
    expect(el.querySelector("svg.rate-chart")).toBeNull();
    expect(el.textContent).not.toContain("0.0%");
    expect(el.textContent).toContain("How Payment Health is calculated");
  });

  it("shows pending-only periods without a fabricated rate", async () => {
    const pendingOnly: PaymentHealth = {
      ...HEALTH,
      summary: { period: counts(0, 0, 2), baseline: counts(21, 4) },
      attention: { status: "no_completed", status_label: "No completed attempts", degraded: [], not_evaluated: [] },
    };
    mockFetch(handlerWith(pendingOnly));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const tile = page.container.querySelector("[aria-label='Success rate']");
    expect(tile?.querySelector(".stat-value")?.textContent).toBe("—");
    expect(tile?.textContent).toContain("No completed attempts to rate");
    expect(page.container.textContent).toContain("2 pending, not counted in the rate");
  });

  it("shows the error state with a retry when the request fails", async () => {
    mockFetch((url) => {
      if (url.startsWith("/api/payment-health")) return { status: 500, body: { error: { code: "server_error", message: "Something went wrong." } } };
      return handlerWith(HEALTH)(url, undefined);
    });
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.querySelector(".state-error")?.textContent).toContain("Could not load this view");
    expect(page.container.querySelector(".state-error button")?.textContent).toBe("Try again");
  });
});
