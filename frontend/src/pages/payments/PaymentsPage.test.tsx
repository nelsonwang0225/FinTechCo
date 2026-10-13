import { afterEach, describe, expect, it } from "vitest";
import { ATTEMPTS, META, PAYMENTS } from "../../test/fixtures";
import { MAYA, SAM, mockFetch, type Handler } from "../../test/mockApi";
import { click, flush, renderPage, setValue, type Rendered } from "../../test/render";
import { PaymentsPage } from "./PaymentsPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

const handler: Handler = (url) => {
  if (url === "/api/session") return { status: 200, body: MAYA };
  if (url === "/api/meta") return { status: 200, body: META };
  if (url.startsWith("/api/payments?")) return { status: 200, body: PAYMENTS };
  if (url.startsWith("/api/attempts?")) return { status: 200, body: ATTEMPTS };
  return undefined;
};

describe("PaymentsPage", () => {
  it("lists payments for the default period with money right-aligned and status as dot plus text", async () => {
    const { calls } = mockFetch(handler);
    page = await renderPage(<PaymentsPage />, "/payments");
    await flush();
    const el = page.container;
    const listCall = calls.find((c) => c.url.startsWith("/api/payments?"));
    expect(listCall?.url).toContain("period=last_7_days");
    expect(listCall?.url).toContain("page_size=25");
    expect(el.textContent).toContain("Showing last 7 days: Sep 29 – Oct 5, 2026");
    const rows = el.querySelectorAll("tbody tr");
    expect(rows.length).toBe(2);
    expect(rows[0]?.textContent).toContain("AL-11404");
    expect(rows[0]?.textContent).toContain("Taylor Reed");
    expect(rows[0]?.textContent).toContain("Partially refunded");
    expect(rows[0]?.textContent).toContain("$343.98");
    expect(rows[1]?.textContent).toContain("Guest");
    expect(rows[1]?.textContent).toContain("In store · Fulton Market");
    const amountHeader = Array.from(el.querySelectorAll("th")).find((th) => th.textContent?.includes("Amount"));
    expect(amountHeader?.classList.contains("money")).toBe(true);
    expect(el.querySelector(".badge .badge-dot")).not.toBeNull();
    expect(el.textContent).toContain("1–2 of 2");
  });

  it("puts a status filter in the URL and refetches with it", async () => {
    const { calls } = mockFetch(handler);
    page = await renderPage(<PaymentsPage />, "/payments");
    await flush();
    await setValue(page.container.querySelector("#payments-status"), "failed");
    await flush();
    const last = calls.filter((c) => c.url.startsWith("/api/payments?")).at(-1);
    expect(last?.url).toContain("status=failed");
    expect(page.container.textContent).toContain("Status: Failed");
  });

  it("switches to the attempts tab, which has its own outcome filter and shows recorded reasons", async () => {
    const { calls } = mockFetch(handler);
    page = await renderPage(<PaymentsPage />, "/payments?tab=attempts");
    await flush();
    const el = page.container;
    expect(el.querySelector("#attempts-outcome")).not.toBeNull();
    expect(el.querySelector("#payments-status")).toBeNull();
    expect(calls.some((c) => c.url.startsWith("/api/attempts?"))).toBe(true);
    expect(el.textContent).toContain("Insufficient funds");
    expect(el.textContent).toContain("Visa •••• 4242");
    const paymentsTab = Array.from(el.querySelectorAll("[role=tab]")).find((t) => t.textContent === "Payments");
    await click(paymentsTab ?? null);
    await flush();
    expect(el.querySelector("#payments-status")).not.toBeNull();
  });

  it("shows the empty state when nothing matches", async () => {
    mockFetch((url) => {
      if (url.startsWith("/api/payments?")) return { status: 200, body: { ...PAYMENTS, items: [], total: 0 } };
      return handler(url, undefined);
    });
    page = await renderPage(<PaymentsPage />, "/payments?q=nothing");
    await flush();
    expect(page.container.textContent).toContain("No payments match");
  });

  it("arrives from Payment Health with the recovery filter applied and a way back", async () => {
    const { calls } = mockFetch(handler);
    page = await renderPage(<PaymentsPage />, "/payments?period=last_7_days&channel=mobile_app&recovery=unresolved&health=period%3Dlast_7_days%26channel%3Dmobile_app");
    await flush();
    const el = page.container;
    expect(calls.filter((c) => c.url.startsWith("/api/payments?")).at(-1)?.url).toContain("recovery=unresolved");
    expect(el.textContent).toContain("Recovery: Unresolved payments");
    const back = Array.from(el.querySelectorAll("a")).find((a) => a.textContent?.includes("Back to Payment Health"));
    expect(back?.getAttribute("href")).toBe("/payment-health?period=last_7_days&channel=mobile_app");
    // The register export has no recovery filter, so it is not offered while one is applied.
    expect(el.querySelector("a[data-export=payments]")).toBeNull();
    // Switching tabs keeps the way back.
    const attemptsTab = Array.from(el.querySelectorAll("[role=tab]")).find((t) => t.textContent === "Attempts");
    await click(attemptsTab ?? null);
    await flush();
    expect(Array.from(el.querySelectorAll("a")).some((a) => a.textContent?.includes("Back to Payment Health"))).toBe(true);
    expect(calls.filter((c) => c.url.startsWith("/api/attempts?")).at(-1)?.url).not.toContain("recovery");
  });

  it("only ever links back to Payment Health, whatever the health parameter holds", async () => {
    mockFetch(handler);
    page = await renderPage(<PaymentsPage />, "/payments?health=" + encodeURIComponent("https://evil.example.com/?period=x&channel=<script>&from=2026-10-01"));
    await flush();
    const back = Array.from(page.container.querySelectorAll("a")).find((a) => a.textContent?.includes("Back to Payment Health"));
    expect(back?.getAttribute("href")).toBe("/payment-health?from=2026-10-01");
    page.unmount();
    mockFetch(handler);
    page = await renderPage(<PaymentsPage />, "/payments");
    await flush();
    expect(Array.from(page.container.querySelectorAll("a")).some((a) => a.textContent?.includes("Back to Payment Health"))).toBe(false);
  });

  it("filters attempts by recorded failure signal", async () => {
    const { calls } = mockFetch(handler);
    page = await renderPage(<PaymentsPage />, "/payments?tab=attempts");
    await flush();
    const el = page.container;
    expect(el.querySelector("a[data-export=attempts]")).not.toBeNull();
    await setValue(el.querySelector("#attempts-signal"), "issuer_unavailable");
    await flush();
    const last = calls.filter((c) => c.url.startsWith("/api/attempts?")).at(-1);
    expect(last?.url).toContain("outcome=failed");
    expect(last?.url).toContain("failure_code=issuer_unavailable");
    expect(el.textContent).toContain("Recorded signal: Issuer unavailable");
    expect(el.querySelector("a[data-export=attempts]")).toBeNull();
  });

  it("offers a CSV export of the current filters to roles with reports:operational only", async () => {
    mockFetch(handler);
    page = await renderPage(<PaymentsPage />, "/payments?status=failed&channel=website");
    await flush();
    expect(page.container.querySelector("a[data-export=payments]")?.getAttribute("href")).toBe("/api/reports/payments.csv?period=last_7_days&status=failed&channel=website&sort=created_at&dir=desc");
    page.unmount();
    mockFetch((url) => (url === "/api/session" ? { status: 200, body: SAM } : handler(url, undefined)));
    page = await renderPage(<PaymentsPage />, "/payments?tab=attempts");
    await flush();
    expect(page.container.querySelector("a[data-export]")).toBeNull();
  });
});
