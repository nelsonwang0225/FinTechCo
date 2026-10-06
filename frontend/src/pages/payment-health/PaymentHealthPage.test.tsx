import { afterEach, describe, expect, it } from "vitest";
import type { ChannelHealth, PaymentHealth } from "../../api/payment-health-types";
import { META } from "../../test/fixtures";
import { MAYA, mockFetch, type Handler } from "../../test/mockApi";
import { flush, renderPage, setValue, type Rendered } from "../../test/render";
import { PaymentHealthPage } from "./PaymentHealthPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

const MOBILE: ChannelHealth = {
  channel: "mobile_app",
  channel_label: "Mobile app",
  succeeded: 134,
  failed: 52,
  pending: 1,
  completed: 186,
  rate_bp: 7204,
  baseline_succeeded: 572,
  baseline_failed: 58,
  baseline_completed: 630,
  baseline_rate_bp: 9079,
  delta_bp: -1875,
  evaluation: "degraded",
  evaluation_label: "Degraded",
};

const WEBSITE: ChannelHealth = {
  ...MOBILE,
  channel: "website",
  channel_label: "Website",
  succeeded: 246,
  failed: 20,
  completed: 266,
  rate_bp: 9248,
  baseline_succeeded: 969,
  baseline_failed: 91,
  baseline_completed: 1060,
  baseline_rate_bp: 9142,
  delta_bp: 107,
  evaluation: "within_range",
  evaluation_label: "Within range",
};

const DEGRADED: PaymentHealth = {
  period: { preset: "last_7_days", label: "Last 7 days", from_date: "2026-09-29", to_date: "2026-10-05", range_label: "Sep 29 – Oct 5, 2026" },
  baseline: { from_date: "2026-08-30", to_date: "2026-09-28", range_label: "Aug 30 – Sep 28, 2026" },
  channel: null,
  channel_label: "All channels",
  rules: { baseline_days: 30, min_period_completed: 30, min_baseline_completed: 100, degraded_drop_bp: 1000 },
  summary: { state: "degraded", message: "Mobile app is degraded: 72.0% success vs 90.8% baseline, 52 failed attempts.", degraded: [MOBILE] },
  kpis: {
    succeeded: 380,
    failed: 72,
    pending: 2,
    completed: 452,
    rate_bp: 8407,
    baseline_completed: 1690,
    baseline_rate_bp: 9118,
    delta_bp: -711,
    affected_payments: 64,
    recovered_payments: 41,
    unresolved_payments: 22,
    awaiting_retry_payments: 1,
    affected_cents: 2334007,
    currency: "USD",
  },
  channels: [WEBSITE, MOBILE],
  failure_signals: [
    { code: "issuer_unavailable", label: "Issuer unavailable", count: 32 },
    { code: "do_not_honor", label: "Do not honor", count: 40 },
  ],
};

function handler(body: PaymentHealth): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: MAYA };
    if (url === "/api/meta") return { status: 200, body: META };
    if (url.startsWith("/api/payment-health")) return { status: 200, body };
    return undefined;
  };
}

describe("PaymentHealthPage", () => {
  it("names the degraded channel with its rate, baseline and failed attempts, and links to its unresolved payments", async () => {
    const { calls } = mockFetch(handler(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(calls.find((c) => c.url.startsWith("/api/payment-health"))?.url).toBe("/api/payment-health?period=last_7_days");
    expect(el.textContent).toContain("Degradation detected");
    expect(el.textContent).toContain("Mobile app is degraded: 72.0% success vs 90.8% baseline, 52 failed attempts.");
    expect(el.textContent).toContain("72.0% vs 90.8% baseline (−18.8 pts) · 52 failed attempts");
    const channelLink = Array.from(el.querySelectorAll("a")).find((a) => a.textContent === "Review unresolved mobile app payments");
    expect(channelLink?.getAttribute("href")).toBe("/payments?period=last_7_days&channel=mobile_app&status=failed");
    expect(el.textContent).toContain("compared with the 30 days before (Aug 30 – Sep 28, 2026)");
  });

  it("shows the KPI row with pending excluded, recovery per payment and value as payment amounts", async () => {
    mockFetch(handler(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const rate = page.container.querySelector("[aria-label='Success rate']");
    expect(rate?.textContent).toContain("84.1%");
    expect(rate?.textContent).toContain("Baseline 91.2% · −7.1 pts");
    expect(rate?.textContent).toContain("452 completed · 2 pending not counted");
    expect(page.container.querySelector("[aria-label='Failed attempts']")?.textContent).toContain("72");
    const affected = page.container.querySelector("[aria-label='Affected payments']");
    expect(affected?.textContent).toContain("64");
    expect(affected?.textContent).toContain("41 recovered · 22 unresolved · 1 awaiting retry");
    expect(page.container.querySelector("[aria-label='Affected value']")?.textContent).toContain("$23,340.07");
    expect(page.container.textContent?.toLowerCase()).not.toContain("lost revenue");
    expect(page.container.textContent?.toLowerCase()).not.toContain("revenue");
  });

  it("lists every channel's evaluation as dot plus text, and failure signals as recorded signals", async () => {
    mockFetch(handler(DEGRADED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const tables = page.container.querySelectorAll("table");
    const channelRows = tables[0]?.querySelectorAll("tbody tr");
    expect(channelRows?.length).toBe(2);
    expect(channelRows?.[0]?.textContent).toContain("Within range");
    expect(channelRows?.[1]?.textContent).toContain("Degraded");
    expect(channelRows?.[1]?.querySelector(".badge-danger .badge-dot")).not.toBeNull();
    expect(page.container.textContent).toContain("As recorded on failed attempts, not confirmed root causes");
    const signalRows = tables[1]?.querySelectorAll("tbody tr");
    expect(signalRows?.[0]?.textContent).toContain("Issuer unavailable");
    expect(signalRows?.[0]?.textContent).toContain("44.4%");
    const rateHeader = Array.from(tables[0]?.querySelectorAll("th") ?? []).find((th) => th.textContent?.includes("Success rate"));
    expect(rateHeader?.classList.contains("money")).toBe(true);
  });

  it("scopes to a channel and custom dates, and keeps them on the unresolved-payments drill-down", async () => {
    const scoped: PaymentHealth = { ...DEGRADED, channel: "mobile_app", channel_label: "Mobile app" };
    const { calls } = mockFetch(handler(scoped));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=custom&from=2026-10-01&to=2026-10-02");
    await flush();
    await setValue(page.container.querySelector("#health-channel"), "mobile_app");
    await flush();
    const last = calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1);
    expect(last?.url).toBe("/api/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app");
    const review = Array.from(page.container.querySelectorAll("a")).find((a) => a.textContent === "Review unresolved payments");
    expect(review?.getAttribute("href")).toBe("/payments?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app&status=failed");
  });

  it("says plainly when nothing is degraded and when there is no data, without inventing a rate", async () => {
    const empty: PaymentHealth = {
      ...DEGRADED,
      summary: { state: "insufficient_volume", message: "Insufficient volume to draw a conclusion: no channel has enough completed attempts in this period and its baseline.", degraded: [] },
      kpis: { ...DEGRADED.kpis, succeeded: 0, failed: 0, pending: 0, completed: 0, rate_bp: null, delta_bp: null, affected_payments: 0, recovered_payments: 0, unresolved_payments: 0, awaiting_retry_payments: 0, affected_cents: 0 },
      channels: [],
      failure_signals: [],
    };
    mockFetch(handler(empty));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(el.textContent).toContain("Not enough volume to evaluate");
    expect(el.querySelector("[aria-label='Success rate'] .stat-value")?.textContent).toBe("—");
    expect(el.textContent).toContain("No completed attempts in this period");
    expect(el.textContent).not.toContain("0.0%");
    expect(el.textContent).toContain("No failed attempts in this period");
    expect(Array.from(el.querySelectorAll("a")).some((a) => a.textContent?.startsWith("Review unresolved"))).toBe(false);
  });

  it("does not compare against a baseline that is too thin", async () => {
    const thin: PaymentHealth = { ...DEGRADED, kpis: { ...DEGRADED.kpis, baseline_completed: 84, baseline_rate_bp: 8929, delta_bp: 60 } };
    mockFetch(handler(thin));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const rate = page.container.querySelector("[aria-label='Success rate']");
    expect(rate?.textContent).toContain("Baseline has 84 completed attempts, too few to compare");
    expect(rate?.textContent).not.toContain("89.3%");
  });

  it("reports no significant degradation when every evaluated channel is within range", async () => {
    const healthy: PaymentHealth = {
      ...DEGRADED,
      summary: { state: "no_degradation", message: "No significant degradation detected in Website.", degraded: [] },
      channels: [WEBSITE],
    };
    mockFetch(handler(healthy));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.querySelector("#attention-heading")?.textContent).toBe("No significant degradation detected");
    expect(page.container.textContent).toContain("No significant degradation detected in Website.");
  });
});
