import { afterEach, describe, expect, it } from "vitest";
import type { PaymentHealth } from "../../api/payment-health-types";
import { HEALTH, META } from "../../test/fixtures";
import { MAYA, mockFetch, type Handler } from "../../test/mockApi";
import { click, flush, renderPage, type Rendered } from "../../test/render";
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
    if (url.startsWith("/api/payment-health")) return "status" in health && "body" in health ? health : { status: 200, body: health };
    return undefined;
  };
}

function hrefOf(el: HTMLElement, text: string): string | null {
  const link = Array.from(el.querySelectorAll("a")).find((a) => a.textContent?.includes(text));
  return link?.getAttribute("href") ?? null;
}

describe("PaymentHealthPage", () => {
  it("asks for the default scope and names the degraded channel with its evidence", async () => {
    const { calls } = mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(calls.find((c) => c.url.startsWith("/api/payment-health"))?.url).toBe("/api/payment-health?period=last_7_days");
    expect(el.textContent).toContain("Mobile app is degraded");
    expect(el.textContent).toContain("72.0% success against a 90.8% baseline (−18.8 pts)");
    expect(el.textContent).toContain("52 failed attempts");
    expect(hrefOf(el, "Review unresolved mobile app payments")).toBe("/payments?period=last_7_days&channel=mobile_app&status=failed&ph=period%3Dlast_7_days");
    expect(el.querySelector(".attention-degraded .attention-dot")).not.toBeNull();
  });

  it("shows the completed-attempt rate against the baseline and says pending attempts are not counted", async () => {
    mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const rate = page.container.querySelector("[aria-label='Success rate']");
    expect(rate?.textContent).toContain("85.6%");
    expect(rate?.textContent).toContain("Baseline 91.6% · −6.0 pts");
    const pending = page.container.querySelector("[aria-label='Pending attempts']");
    expect(pending?.textContent).toContain("2");
    expect(pending?.textContent).toContain("not counted in the success rate");
  });

  it("scopes the page to a channel when its row is selected, and marks the row", async () => {
    const { calls } = mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=month_to_date");
    await flush();
    const button = Array.from(page.container.querySelectorAll("button.link-button")).find((b) => b.textContent === "Mobile app");
    await click(button ?? null);
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=month_to_date&channel=mobile_app");
    const selected = page.container.querySelector("tr[aria-current='true']");
    expect(selected?.textContent).toContain("Mobile app");
    expect(selected?.querySelector("button")?.getAttribute("aria-pressed")).toBe("true");
    expect((page.container.querySelector("#health-channel") as HTMLSelectElement).value).toBe("mobile_app");
  });

  it("lists recorded failure signals, each linking to the matching failed attempts", async () => {
    mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?channel=mobile_app");
    await flush();
    const el = page.container;
    expect(el.textContent).toContain("not confirmed root causes");
    expect(hrefOf(el, "Issuer unavailable")).toBe(
      "/payments?tab=attempts&period=last_7_days&channel=mobile_app&outcome=failed&failure_code=issuer_unavailable&ph=period%3Dlast_7_days%26channel%3Dmobile_app",
    );
  });

  it("counts affected, recovered and unresolved payments once each, as payment amounts", async () => {
    mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    const recovery = el.querySelector(".health-recovery");
    expect(recovery?.textContent).toContain("Affected payments");
    expect(recovery?.textContent).toContain("$12,345.67");
    expect(recovery?.textContent).toContain("57 within 60 min of the first attempt");
    expect(recovery?.textContent).toContain("$2,345.67");
    expect(recovery?.textContent).not.toContain("Retry pending");
    expect(el.textContent).toContain("payment amounts, not revenue");
    expect(el.textContent).not.toMatch(/lost revenue|revenue lost/i);
    expect(el.textContent).toContain("AL-13020");
    expect(hrefOf(el, "Review all 12 in Payments")).toBe("/payments?period=last_7_days&status=failed&ph=period%3Dlast_7_days");
    expect(el.textContent).toContain("Showing the 1 most recent of 12");
  });

  it("states plainly when no channel is degraded and which channels were not judged", async () => {
    mockFetch(
      handlerWith({
        ...HEALTH,
        attention: { verdict: "no_degradation", degraded_channels: [] },
        channels: HEALTH.channels.map((c) =>
          c.channel === "mobile_app" ? { ...c, verdict: "insufficient_data", verdict_label: "Not enough data", period: { ...c.period, completed: 12 } } : c,
        ),
      }),
    );
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(el.textContent).toContain("No significant degradation detected");
    expect(el.textContent).not.toContain("is degraded");
    expect(el.textContent).toContain("Not judged, too few completed attempts: Mobile app (12 in the period, 630 in the baseline)");
  });

  it("shows an empty state instead of a rate when nothing completed", async () => {
    const empty: PaymentHealth = {
      ...HEALTH,
      summary: { ...HEALTH.summary, period: { succeeded: 0, failed: 0, pending: 2, completed: 0, success_rate_bp: null }, change_bp: null },
      attention: { verdict: "no_data", degraded_channels: [] },
      channels: HEALTH.channels.map((c) => ({ ...c, verdict: "no_data", verdict_label: "No completed attempts" })),
      failure_signals: [],
      unresolved_payments: [],
      unresolved_total: 0,
    };
    mockFetch(handlerWith(empty));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?from=2026-10-05&to=2026-10-05&period=custom");
    await flush();
    const el = page.container;
    expect(el.textContent).toContain("No completed attempts in this period");
    expect(el.textContent).toContain("2 attempts are still pending");
    expect(el.querySelector("[aria-label='Success rate']")).toBeNull();
    expect(el.querySelector(".line-chart")).toBeNull();
    expect(el.textContent).toContain("No failed attempts in this period");
    expect(el.textContent).toContain("No unresolved payments");
  });

  it("draws the daily trend with the baseline, a gap for a day with no completed attempts and a low-volume marker", async () => {
    mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const chart = page.container.querySelector(".line-chart");
    expect(chart?.querySelector(".chart-reference")).not.toBeNull();
    expect(chart?.querySelectorAll(".chart-line").length).toBe(2);
    expect(chart?.querySelector(".chart-gap[data-day='Oct 3']")).not.toBeNull();
    expect(chart?.querySelector(".chart-point-low[data-day='Oct 2']")).not.toBeNull();
    const desc = chart?.querySelector("desc")?.textContent ?? "";
    expect(desc).toContain("Oct 2: 62.5% · 5 succeeded, 3 failed · low volume");
    expect(desc).toContain("Oct 3: no completed attempts (1 pending)");
    expect(page.container.textContent).toContain("Baseline 91.6% (Aug 30 – Sep 28, 2026)");
  });

  it("defines every term from the rules the server applied", async () => {
    mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const defs = page.container.querySelector(".health-definitions")?.textContent ?? "";
    for (const term of ["Success rate", "Baseline", "Degraded", "Affected payment", "Recovered", "Unresolved"]) expect(defs).toContain(term);
    expect(defs).toContain("10.0 percentage points or more below its baseline");
    expect(defs).toContain("at least 50 completed attempts and the baseline at least 200");
  });

  it("renders the error and forbidden states", async () => {
    mockFetch(handlerWith({ status: 500, body: { error: { code: "server_error", message: "Something broke." } } }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.textContent).toContain("Could not load this view");
    page.unmount();
    mockFetch(handlerWith({ status: 403, body: { error: { code: "forbidden", message: "Your role does not include payments:read." } } }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.textContent).toContain("Your role does not include this section");
  });
});
