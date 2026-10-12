import { afterEach, describe, expect, it } from "vitest";
import type { PaymentHealth } from "../../api/payment-health-types";
import { HEALTH, HEALTH_EMPTY, META } from "../../test/fixtures";
import { MAYA, mockFetch, type Handler } from "../../test/mockApi";
import { click, flush, renderPage, setValue, type Rendered } from "../../test/render";
import { PaymentHealthPage } from "./PaymentHealthPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

function handlerWith(health: PaymentHealth | ((url: string) => PaymentHealth), status = 200): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: MAYA };
    if (url === "/api/meta") return { status: 200, body: META };
    if (url.startsWith("/api/payment-health")) {
      if (status !== 200) return { status, body: { error: { code: "forbidden", message: "Your role cannot view this." } } };
      return { status: 200, body: typeof health === "function" ? health(url) : health };
    }
    return undefined;
  };
}

function hrefs(el: Element): string[] {
  return Array.from(el.querySelectorAll("a")).map((a) => a.getAttribute("href") ?? "");
}

const RETURN = "ph_period=last_7_days";

describe("PaymentHealthPage", () => {
  it("fetches the default period for all channels and names the degraded channel with its evidence", async () => {
    const { calls } = mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(calls.find((c) => c.url.startsWith("/api/payment-health"))?.url).toBe("/api/payment-health?period=last_7_days");
    const attention = page.container.querySelector(".health-attention");
    expect(attention?.querySelector("h2")?.textContent).toBe("1 channel is degraded");
    expect(attention?.textContent).toContain("Mobile app: 72.0% success rate vs 90.8% baseline (−18.8 pts)");
    expect(attention?.textContent).toContain("52 failed attempts · 16 unresolved payments");
    expect(hrefs(attention!)).toEqual([
      `/payments?tab=attempts&period=last_7_days&outcome=failed&channel=mobile_app&${RETURN}`,
      `/payments?period=last_7_days&status=failed&channel=mobile_app&${RETURN}`,
    ]);
  });

  it("shows completed-attempt tiles with pending excluded and per-payment recovery as payment amounts", async () => {
    mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const tile = (name: string) => page!.container.querySelector(`[aria-label='${name}']`)?.textContent ?? "";
    expect(tile("Success rate")).toBe("Success rate · completed attempts84.7%Baseline 91.3% · −6.6 pts589 completed attempts · 2 pending, not counted");
    expect(tile("Failed attempts")).toContain("90of 589 completed attempts · 499 succeeded");
    expect(tile("Affected payments")).toBe("Affected payments83$23,340.07 in payment amounts55 recovered · 55 within 1 hour");
    expect(tile("Unresolved payments")).toContain("28$7,622.73 in payment amounts");
    // The only mention of lost revenue is the definition saying these amounts are not that.
    expect(page.container.textContent?.match(/lost revenue/gi)).toEqual(["lost revenue"]);
    expect(page.container.textContent).toContain("They are not lost revenue.");
  });

  it("charts the daily rate against the baseline and lists recorded failure signals linked to their attempts", async () => {
    mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(el.querySelector("svg.rate-chart title")?.textContent).toBe("Daily success rate, All channels, Sep 29 – Oct 5, 2026");
    expect(el.querySelectorAll(".chart-point").length).toBe(7);
    expect(el.querySelector(".chart-baseline title")?.textContent).toBe("Baseline, Aug 30 – Sep 28, 2026: 91.3%");
    expect(el.textContent).toContain("Recorded failure signals");
    expect(el.textContent).toContain("not confirmed causes");
    const signal = Array.from(el.querySelectorAll("a")).find((a) => a.textContent === "Issuer unavailable");
    expect(signal?.getAttribute("href")).toBe(`/payments?tab=attempts&period=last_7_days&outcome=failed&failure_code=issuer_unavailable&${RETURN}`);
  });

  it("scopes the page to a channel when its row is selected, and carries that scope into drill-downs", async () => {
    const { calls } = mockFetch(handlerWith((url) => (url.includes("channel=mobile_app") ? { ...HEALTH, channel: "mobile_app", channel_label: "Mobile app" } : HEALTH)));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=custom&from=2026-10-01&to=2026-10-02");
    await flush();
    const button = Array.from(page.container.querySelectorAll("button.link-button")).find((b) => b.textContent === "Mobile app");
    expect(button?.getAttribute("aria-pressed")).toBe("false");
    await click(button ?? null);
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app");
    const selected = page.container.querySelector("button.link-button[aria-pressed=true]");
    expect(selected?.textContent).toBe("Mobile app · showing");
    const review = Array.from(page.container.querySelectorAll("a")).find((a) => a.textContent?.startsWith("Review all"));
    expect(review?.getAttribute("href")).toBe(
      "/payments?period=custom&from=2026-10-01&to=2026-10-02&status=failed&channel=mobile_app&ph_period=custom&ph_from=2026-10-01&ph_to=2026-10-02&ph_channel=mobile_app",
    );
    await click(Array.from(page.container.querySelectorAll("button")).find((b) => b.textContent === "Show all channels") ?? null);
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=custom&from=2026-10-01&to=2026-10-02");
  });

  it("refetches when the channel filter or the period changes", async () => {
    const { calls } = mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    await setValue(page.container.querySelector("#health-channel"), "in_store");
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=last_7_days&channel=in_store");
    await setValue(page.container.querySelector("#health-period-preset"), "month_to_date");
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/payment-health")).at(-1)?.url).toBe("/api/payment-health?period=month_to_date&channel=in_store");
  });

  it("lists the first unresolved payments with links to each payment", async () => {
    mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const table = Array.from(page.container.querySelectorAll("table")).find((t) => t.querySelector("caption")?.textContent?.includes("unresolved"));
    expect(table?.querySelector("caption")?.textContent).toBe("First 2 of 28 unresolved payments, oldest first");
    const rows = table?.querySelectorAll("tbody tr") ?? [];
    expect(rows.length).toBe(2);
    expect(rows[1]?.textContent).toContain("AL-12183");
    expect(rows[1]?.textContent).toContain("Issuer unavailable");
    expect(rows[1]?.querySelector("a")?.getAttribute("href")).toBe("/payments/pay_unresolved00002");
    expect(page.container.textContent).toContain("Review all 28 in Payments");
  });

  it("says plainly when nothing is degraded and which channels had too few attempts", async () => {
    mockFetch(handlerWith({ ...HEALTH, attention: { status: "no_significant_degradation", degraded: [], insufficient_volume_channels: ["in_store"] } }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const attention = page.container.querySelector(".health-attention");
    expect(attention?.querySelector("h2")?.textContent).toBe("No significant degradation detected");
    expect(attention?.textContent).toContain("within 10.0 pts of its own baseline");
    expect(attention?.textContent).toContain("Not enough attempts to assess: In store.");
  });

  it("flags a low-volume rate on its tile instead of presenting it as a comparison", async () => {
    const low = { ...HEALTH.attempts, succeeded: 4, failed: 0, pending: 2, completed: 4, success_rate_bp: 10000, change_bp: 1739 };
    mockFetch(handlerWith({ ...HEALTH, attempts: low }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.querySelector("[aria-label='Success rate'] .stat-caution")?.textContent).toBe(
      "Low volume: fewer than 20 completed attempts here or in the baseline, so this is not compared.",
    );
    page.unmount();
    mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.querySelector(".stat-caution")).toBeNull();
  });

  it("draws no conclusion when no channel has enough attempts", async () => {
    mockFetch(handlerWith({ ...HEALTH, attention: { status: "insufficient_volume", degraded: [], insufficient_volume_channels: ["website", "mobile_app"] } }));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const attention = page.container.querySelector(".health-attention");
    expect(attention?.querySelector("h2")?.textContent).toBe("Not enough completed attempts to assess");
    expect(attention?.textContent).toContain("at least 20 completed attempts in the period and in its baseline");
  });

  it("shows empty states rather than a fabricated rate when nothing completed", async () => {
    mockFetch(handlerWith(HEALTH_EMPTY));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const el = page.container;
    expect(el.querySelector(".health-attention h2")?.textContent).toBe("No completed attempts in this period");
    expect(el.querySelector("[aria-label='Success rate'] .stat-value")?.textContent).toBe("—");
    expect(el.querySelector("svg.rate-chart")).toBeNull();
    expect(el.textContent).toContain("There is no success rate to chart for this period.");
    expect(el.textContent).toContain("No failure signals were recorded in this period.");
    expect(el.textContent).toContain("No unresolved payments");
  });

  it("defines every term with the thresholds the backend applied", async () => {
    mockFetch(handlerWith(HEALTH));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    const defs = page.container.querySelector(".health-definitions")?.textContent ?? "";
    for (const term of ["Success rate", "Baseline", "Degraded", "Affected payment", "Recovered", "Unresolved", "Retry pending", "Recorded failure signal"]) {
      expect(defs).toContain(term);
    }
    expect(defs).toContain("at least 10.0 pts below the channel's own baseline, with at least 20 completed attempts");
    expect(defs).toContain("within 60 minutes of its first attempt");
    expect(defs).toContain("not a confirmed root cause");
  });

  it("shows the 403 state and no figures when the API refuses", async () => {
    mockFetch(handlerWith(HEALTH, 403));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.querySelector(".health")).toBeNull();
    expect(page.container.querySelector(".state-forbidden")?.textContent).toContain("Your role does not include this section");
  });
});
