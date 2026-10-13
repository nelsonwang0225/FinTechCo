import { afterEach, describe, expect, it } from "vitest";
import type { PaymentHealth } from "../../api/payment-health-types";
import { META, PAYMENT_HEALTH } from "../../test/fixtures";
import { DANIEL, MAYA, mockFetch, type Handler } from "../../test/mockApi";
import { click, flush, renderPage, setValue, type Rendered } from "../../test/render";
import { PaymentHealthPage } from "./PaymentHealthPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

function handlerWith(health: PaymentHealth | { status: number; body: unknown }): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: MAYA };
    if (url === "/api/meta") return { status: 200, body: META };
    if (url.startsWith("/api/payment-health")) return "status" in health ? health : { status: 200, body: health };
    return undefined;
  };
}

async function open(path: string, health: PaymentHealth | { status: number; body: unknown } = PAYMENT_HEALTH) {
  const recorded = mockFetch(handlerWith(health));
  page = await renderPage(<PaymentHealthPage />, path);
  await flush();
  return { el: page.container, calls: recorded.calls };
}

function link(el: HTMLElement, text: string): HTMLAnchorElement | undefined {
  return Array.from(el.querySelectorAll("a")).find((a) => a.textContent?.includes(text));
}

describe("PaymentHealthPage", () => {
  it("names the degraded channel with its rate, baseline and failed attempts, and links to its unresolved payments", async () => {
    const { el, calls } = await open("/payment-health");
    expect(calls.find((c) => c.url.startsWith("/api/payment-health"))?.url).toBe("/api/payment-health?period=last_7_days");
    const attention = el.querySelector(".health-attention");
    expect(attention?.textContent).toContain("Mobile app is below baseline");
    expect(attention?.textContent).toContain("72.0% success against a 90.8% baseline (−18.8 pts), 52 failed attempts.");
    expect(attention?.querySelector(".badge .badge-dot")).not.toBeNull();
    expect(link(el, "Review unresolved mobile app payments")?.getAttribute("href")).toBe(
      "/payments?period=last_7_days&channel=mobile_app&status=failed&back=period%3Dlast_7_days",
    );
  });

  it("shows completed-attempt metrics with the pending count kept out of the rate", async () => {
    const { el } = await open("/payment-health");
    const card = (label: string) => el.querySelector(`section[aria-label='${label}']`)?.textContent ?? "";
    expect(card("Success rate")).toContain("84.7%");
    expect(card("Success rate")).toContain("Baseline 91.3% · −6.6 pts");
    expect(card("Failed attempts")).toContain("90");
    expect(card("Completed attempts")).toContain("589");
    expect(card("Completed attempts")).toContain("2 pending attempts, not counted in rates");
    expect(card("Affected payments")).toContain("$23,340.07 payment value");
    expect(el.textContent).not.toMatch(/lost revenue/i);
  });

  it("draws the trend with a baseline, a gap for a day without completed attempts and a hollow low-volume marker", async () => {
    const { el } = await open("/payment-health");
    const svg = el.querySelector("svg.rate-chart");
    expect(svg?.querySelector(".chart-baseline")).not.toBeNull();
    expect(svg?.querySelectorAll(".chart-line").length).toBe(2);
    expect(svg?.querySelectorAll(".chart-point-empty circle").length).toBe(0);
    expect(svg?.querySelectorAll(".chart-point-low").length).toBe(1);
    expect(svg?.querySelector("desc")?.textContent).toContain("Sep 30: no completed attempts");
    expect(svg?.querySelector("desc")?.textContent).toContain("Oct 5: 83.3% (low volume), 5 succeeded, 1 failed, 2 pending (today, so far)");
  });

  it("lists recorded failure signals, never as root causes, each linking to its failed attempts", async () => {
    const { el } = await open("/payment-health?channel=mobile_app", { ...PAYMENT_HEALTH, channel: "mobile_app" });
    expect(el.textContent).toContain("Recorded failure signals");
    expect(el.textContent).toContain("not a confirmed root cause");
    expect(el.textContent).not.toMatch(/root causes? (is|are) /i);
    expect(link(el, "Issuer unavailable")?.getAttribute("href")).toBe(
      "/payments?tab=attempts&period=last_7_days&channel=mobile_app&outcome=failed&failure_code=issuer_unavailable&back=period%3Dlast_7_days%26channel%3Dmobile_app",
    );
  });

  it("counts recovery by payment and links to all unresolved payments", async () => {
    const { el } = await open("/payment-health?period=custom&from=2026-10-01&to=2026-10-02");
    const recovery = el.querySelector("section[aria-labelledby='recovery-heading']")?.textContent ?? "";
    expect(recovery).toContain("Affected payments · 83");
    expect(recovery).toContain("Recovered by a later attempt · 55");
    expect(recovery).toContain("Recovered within 60 minutes of the first attempt · 55");
    expect(recovery).toContain("Unresolved · 28");
    expect(recovery).toContain("$7,622.73");
    expect(recovery).not.toContain("Retry in progress");
    expect(link(el, "Review all 28 in Payments")?.getAttribute("href")).toBe(
      "/payments?period=custom&from=2026-10-01&to=2026-10-02&status=failed&back=period%3Dcustom%26from%3D2026-10-01%26to%3D2026-10-02",
    );
    expect(el.textContent).toContain("Showing the newest 1 of 28.");
  });

  it("scopes the page to a channel from the table and from the filter, through the URL", async () => {
    const { el, calls } = await open("/payment-health");
    const appButton = Array.from(el.querySelectorAll("button[aria-pressed]")).find((b) => b.textContent === "Mobile app");
    expect(appButton?.getAttribute("aria-pressed")).toBe("false");
    await click(appButton ?? null);
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=last_7_days&channel=mobile_app");
    await setValue(el.querySelector("#health-channel"), "website");
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=last_7_days&channel=website");
  });

  it("says plainly when no significant degradation is detected", async () => {
    const healthy: PaymentHealth = {
      ...PAYMENT_HEALTH,
      attention: { state: "ok", degraded_channels: [], insufficient_channels: ["mobile_app"] },
    };
    const { el } = await open("/payment-health", healthy);
    expect(el.querySelector(".health-attention")?.textContent).toContain("No significant degradation detected");
    expect(el.textContent).toContain("within 5.0 pts of its own baseline");
    expect(el.textContent).toContain("Not enough completed attempts to judge: Mobile app.");
  });

  it("draws no conclusion when volume is too low", async () => {
    const low: PaymentHealth = { ...PAYMENT_HEALTH, attention: { state: "insufficient_data", degraded_channels: [], insufficient_channels: ["mobile_app"] } };
    const { el } = await open("/payment-health", low);
    const attention = el.querySelector(".health-attention")?.textContent ?? "";
    expect(attention).toContain("Not enough completed attempts to judge");
    expect(attention).toContain("at least 30 completed attempts in the period and 100 in its baseline");
    expect(attention).not.toContain("below baseline");
  });

  it("shows an empty state instead of a success rate when nothing completed", async () => {
    const empty: PaymentHealth = {
      ...PAYMENT_HEALTH,
      scope: { period: { succeeded: 0, failed: 0, pending: 2, completed: 0, success_rate_bps: null, failure_rate_bps: null }, baseline: PAYMENT_HEALTH.scope.baseline, change_bps: null },
      attention: { state: "no_data", degraded_channels: [], insufficient_channels: [] },
      trend: [{ day: "2026-10-05", succeeded: 0, failed: 0, pending: 2, success_rate_bps: null, low_volume: false, partial: true }],
      failure_signals: [],
      recovery: { ...PAYMENT_HEALTH.recovery, affected_count: 0, affected_cents: 0, recovered_count: 0, recovered_cents: 0, recovered_within_hour_count: 0, recovered_within_hour_cents: 0, unresolved_count: 0, unresolved_cents: 0 },
      unresolved_payments: [],
    };
    const { el } = await open("/payment-health", empty);
    expect(el.querySelector("section[aria-label='Success rate'] .stat-value")?.textContent).toBe("—");
    expect(el.querySelector("svg.rate-chart")).toBeNull();
    expect(el.textContent).toContain("No completed attempts in this period");
    expect(el.textContent).toContain("2 pending attempts are still waiting for a result");
    expect(el.textContent).toContain("No failed attempts");
    expect(el.textContent).toContain("No unresolved payments");
  });

  it("defines every term in the product", async () => {
    const { el } = await open("/payment-health");
    const terms = Array.from(el.querySelectorAll(".health-definitions dt")).map((dt) => dt.textContent);
    expect(terms).toEqual(expect.arrayContaining(["Success rate", "Baseline", "Degraded", "Affected payment", "Recovered", "Unresolved", "Recorded failure signal"]));
    expect(el.querySelector(".health-definitions")?.textContent).toContain("Aug 30 – Sep 28, 2026");
  });

  it("renders the loading, error and forbidden states", async () => {
    mockFetch((url) => (url === "/api/session" ? { status: 200, body: DANIEL } : url === "/api/meta" ? { status: 200, body: META } : undefined));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    expect(page.container.querySelector(".state-loading, .state-error, .state-notfound")).not.toBeNull();
    page.unmount();

    const failed = await open("/payment-health", { status: 500, body: { error: { code: "internal", message: "Boom" } } });
    expect(failed.el.querySelector(".state-error")?.textContent).toContain("Could not load this view");
    page?.unmount();

    const forbidden = await open("/payment-health", { status: 403, body: { error: { code: "forbidden", message: "Your role does not include payments:read." } } });
    expect(forbidden.el.querySelector(".state-forbidden")).not.toBeNull();
  });
});
