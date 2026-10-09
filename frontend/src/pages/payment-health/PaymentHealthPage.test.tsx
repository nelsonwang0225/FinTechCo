import { afterEach, describe, expect, it } from "vitest";
import type { PaymentHealth } from "../../api/payment-health-types";
import { RequirePermission } from "../../session/RequirePermission";
import { META, PAYMENT_HEALTH } from "../../test/fixtures";
import { MAYA, SAM, mockFetch, type Handler } from "../../test/mockApi";
import { click, flush, renderPage, setValue, type Rendered } from "../../test/render";
import { PaymentHealthPage } from "./PaymentHealthPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

function handler(body: PaymentHealth = PAYMENT_HEALTH, status = 200): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: MAYA };
    if (url === "/api/meta") return { status: 200, body: META };
    if (url.startsWith("/api/payment-health")) return { status, body: status === 200 ? body : { error: { code: "internal", message: "Something went wrong." } } };
    return undefined;
  };
}

async function open(path = "/payment-health", h: Handler = handler()) {
  const fetched = mockFetch(h);
  page = await renderPage(<PaymentHealthPage />, path);
  await flush();
  return { el: page.container, calls: fetched.calls };
}

const hrefs = (el: Element, text: string) => Array.from(el.querySelectorAll("a")).filter((a) => a.textContent?.includes(text)).map((a) => a.getAttribute("href"));
const SCOPE = "period=last_7_days&health_period=last_7_days";

describe("PaymentHealthPage", () => {
  it("requests the default scope and names the degraded channel with its evidence", async () => {
    const { el, calls } = await open();
    expect(new Set(calls.filter((c) => c.url.startsWith("/api/payment-health")).map((c) => c.url))).toEqual(new Set(["/api/payment-health?period=last_7_days"]));
    expect(el.textContent).toContain("Showing last 7 days: Sep 29 – Oct 5, 2026 · All channels · compared with the 30 days before (Aug 30 – Sep 28, 2026)");
    const degraded = el.querySelector(".attention-degraded");
    expect(degraded?.textContent).toContain("Mobile app is degraded");
    expect(degraded?.textContent).toContain("72.0% success against a 90.8% baseline (−18.8 pts) · 52 failed attempts");
    expect(hrefs(el, "Review unresolved mobile app payments")).toEqual([`/payments?status=failed&period=last_7_days&channel=mobile_app&health_period=last_7_days`]);
    expect(hrefs(el, "View failed attempts")).toEqual([`/payments?tab=attempts&outcome=failed&period=last_7_days&channel=mobile_app&health_period=last_7_days`]);
  });

  it("shows completed-attempt figures against the baseline, with pending attempts kept out of the rate", async () => {
    const { el } = await open();
    const tile = (name: string) => el.querySelector(`[aria-label='${name}']`)?.textContent ?? "";
    expect(tile("Success rate")).toContain("84.7%");
    expect(tile("Success rate")).toContain("Baseline 91.3% · −6.6 pts");
    expect(tile("Success rate")).toContain("589 completed attempts");
    expect(tile("Failed attempts")).toContain("90");
    expect(tile("Pending attempts")).toContain("2");
    expect(tile("Pending attempts")).toContain("Not counted in the success rate");
    expect(tile("Affected payments")).toContain("55 recovered · 28 unresolved");
    expect(hrefs(el, "Review failed attempts")).toEqual([`/payments?tab=attempts&outcome=failed&${SCOPE}`]);
    expect(hrefs(el, "View pending attempts")).toEqual([`/payments?tab=attempts&outcome=pending&${SCOPE}`]);
  });

  it("charts the daily rate against the baseline with low-volume days marked and counts per point", async () => {
    const { el } = await open();
    const chart = el.querySelector("svg.line-chart");
    expect(chart?.querySelector("title")?.textContent).toBe("Completed-attempt success rate by day, all channels, Sep 29 – Oct 5, 2026");
    expect(chart?.querySelectorAll(".chart-point").length).toBe(7);
    expect(chart?.querySelectorAll(".chart-point.low-volume").length).toBe(1);
    expect(chart?.querySelector(".chart-reference")).not.toBeNull();
    expect(chart?.querySelector("desc")?.textContent).toContain("Oct 1: 68.9% · 84 succeeded, 38 failed, 0 pending");
    expect(chart?.querySelector(".low-volume title")?.textContent).toBe("Oct 5: 92.3% · 12 succeeded, 1 failed, 2 pending · low volume");
    expect(el.textContent).toContain("Low volume: fewer than 20 completed attempts");
    expect(el.querySelectorAll("svg.line-chart a").length).toBe(0);
  });

  it("scopes the page to a channel from the channel table and from the filter", async () => {
    const { el, calls } = await open();
    const table = el.querySelector("table");
    expect(el.querySelector("caption")?.textContent).toBe("Performance by channel");
    const rows = Array.from(table!.querySelectorAll("tbody tr"));
    expect(rows.map((r) => r.querySelector("td")?.textContent)).toEqual(["Website", "Mobile app", "In store"]);
    expect(rows[1]?.textContent).toContain("72.0%");
    expect(rows[1]?.textContent).toContain("Degraded");
    await click(rows[1]!.querySelector("button"));
    await flush();
    expect(calls.at(-1)?.url).toBe("/api/payment-health?period=last_7_days&channel=mobile_app");
    await setValue(el.querySelector("#health-channel"), "in_store");
    await flush();
    expect(calls.at(-1)?.url).toBe("/api/payment-health?period=last_7_days&channel=in_store");
  });

  it("links each recorded failure signal to exactly its failed attempts and never claims a root cause", async () => {
    const { el } = await open("/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app");
    expect(el.textContent).toContain("Recorded failure signals");
    expect(el.textContent).toContain("not confirmed root causes");
    expect(hrefs(el, "Issuer unavailable")).toEqual([
      "/payments?tab=attempts&outcome=failed&failure_code=issuer_unavailable&period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app" +
        "&health_period=custom&health_from=2026-10-01&health_to=2026-10-02&health_channel=mobile_app",
    ]);
  });

  it("shows recovery per payment as payment amounts, and the first unresolved payments", async () => {
    const { el } = await open();
    const recovery = el.querySelector("[aria-labelledby='health-recovery-heading']")?.textContent ?? "";
    expect(recovery).toContain("Affected payments83 · $23,340.07");
    expect(recovery).toContain("Recovered on retry54 within 1 hour of the first attempt55 · $15,717.34");
    expect(recovery).toContain("Retry in progress0 · $0.00");
    expect(recovery).toContain("Unresolved28 · $7,622.73");
    expect(el.textContent?.toLowerCase()).not.toContain("lost revenue");
    expect(el.textContent?.toLowerCase()).not.toContain("revenue");
    expect(hrefs(el, "Review all 28 in Payments")).toEqual([`/payments?status=failed&${SCOPE}`]);
    expect(el.textContent).toContain("AL-12077");
    expect(el.textContent).toContain("Showing the 1 most recent of 28.");
  });

  it("defines every figure from the rules the API applied", async () => {
    const { el } = await open();
    const defs = el.querySelector(".definitions")?.textContent ?? "";
    for (const term of ["Success rate", "Baseline", "Degraded", "Affected payment", "Recovered", "Unresolved", "Recorded failure signal"]) expect(defs).toContain(term);
    expect(defs).toContain("at least 10.0 pts below the channel's baseline");
    expect(defs).toContain("at least 50 completed attempts in the period and 200 in the baseline");
  });

  it("says plainly when nothing is degraded and which channels lack volume", async () => {
    const healthy: PaymentHealth = {
      ...PAYMENT_HEALTH,
      attention: { state: "healthy", state_label: "No significant degradation detected", degraded_channels: [] },
      channels: [
        { ...PAYMENT_HEALTH.channels[2]! },
        { ...PAYMENT_HEALTH.channels[1]!, completed: 7, succeeded: 6, failed: 1, baseline_completed: 25, assessment: "insufficient_volume", assessment_label: "Not enough volume" },
      ],
    };
    const { el } = await open("/payment-health", handler(healthy));
    expect(el.querySelector(".attention-degraded")).toBeNull();
    expect(el.querySelector(".attention-healthy")?.textContent).toContain("No significant degradation detected");
    expect(el.querySelector(".attention-healthy")?.textContent).toContain("within 10.0 pts of its own baseline");
    expect(el.textContent).toContain("No conclusion is drawn for Mobile app (7 of 50 completed attempts in the period; 25 of 200 in the baseline)");
  });

  it("draws no conclusion and no baseline line when the baseline is too thin", async () => {
    const thin: PaymentHealth = {
      ...PAYMENT_HEALTH,
      attention: { state: "insufficient_volume", state_label: "Not enough volume to evaluate", degraded_channels: [] },
      summary: { ...PAYMENT_HEALTH.summary, baseline: { succeeded: 80, failed: 5, completed: 85, success_rate_bp: 9412 }, change_bp: -940 },
      channels: PAYMENT_HEALTH.channels.map((c) => ({ ...c, baseline_completed: 30, assessment: "insufficient_volume" as const, assessment_label: "Not enough volume" })),
    };
    const { el } = await open("/payment-health?period=last_30_days", handler(thin));
    expect(el.textContent).toContain("Not enough volume to evaluate any channel");
    expect(el.textContent).not.toContain("is degraded");
    expect(el.querySelector(".chart-reference")).toBeNull();
    expect(el.textContent).toContain("Baseline not drawn: 85 completed attempts in Aug 30 – Sep 28, 2026, fewer than the 200 needed for a comparison.");
  });

  it("shows an empty state, not a fabricated rate, when nothing completed", async () => {
    const pendingOnly: PaymentHealth = {
      ...PAYMENT_HEALTH,
      channel: "website",
      channel_label: "Website",
      summary: { succeeded: 0, failed: 0, pending: 2, completed: 0, success_rate_bp: null, baseline: { succeeded: 0, failed: 0, completed: 0, success_rate_bp: null }, change_bp: null },
      trend: [{ day: "2026-10-05", succeeded: 0, failed: 0, pending: 2, success_rate_bp: null, low_volume: false }],
      failure_signals: [],
      recovery: { ...PAYMENT_HEALTH.recovery, affected_payments: 0, recovered_payments: 0, recovered_within_hour_payments: 0, unresolved_payments: 0 },
      unresolved_payments: [],
    };
    const { el } = await open("/payment-health?period=custom&from=2026-10-05&to=2026-10-05&channel=website", handler(pendingOnly));
    expect(el.textContent).toContain("No completed attempts · Website");
    expect(el.textContent).toContain("2 attempts are still pending and not counted in a success rate");
    expect(el.querySelector("[aria-label='Success rate']")).toBeNull();
    expect(el.querySelector("svg.line-chart")).toBeNull();
    expect(el.textContent).not.toMatch(/\b0\.0%|100\.0%/);
  });

  it("shows the error state when the view cannot load", async () => {
    const { el } = await open("/payment-health", handler(PAYMENT_HEALTH, 500));
    expect(el.textContent).toContain("Could not load this view");
  });

  it("is forbidden without payments:read", async () => {
    const noPayments = { ...SAM, permissions: ["overview:read"] as typeof SAM.permissions };
    mockFetch((url) => (url === "/api/session" ? { status: 200, body: noPayments } : url === "/api/meta" ? { status: 200, body: META } : undefined));
    page = await renderPage(
      <RequirePermission permission="payments:read">
        <PaymentHealthPage />
      </RequirePermission>,
      "/payment-health",
    );
    await flush();
    expect(page.container.textContent).toContain("Your role does not include this section");
  });
});
