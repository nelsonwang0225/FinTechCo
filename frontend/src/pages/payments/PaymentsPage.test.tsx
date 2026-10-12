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

describe("PaymentsPage drill-down from Payment Health", () => {
  const withSignals: Handler = (url) => {
    if (url === "/api/attempts/failure-signals") {
      return { status: 200, body: { options: [{ value: "issuer_unavailable", label: "Issuer unavailable" }, { value: "do_not_honor", label: "Do not honor" }] } };
    }
    return handler(url, undefined);
  };

  it("filters attempts by recorded failure signal, names it in a chip and exports the same filter", async () => {
    const { calls } = mockFetch(withSignals);
    page = await renderPage(<PaymentsPage />, "/payments?tab=attempts&period=last_7_days&outcome=failed&channel=mobile_app&failure_code=issuer_unavailable");
    await flush();
    const el = page.container;
    const list = calls.filter((c) => c.url.startsWith("/api/attempts?")).at(-1);
    expect(list?.url).toContain("outcome=failed&failure_code=issuer_unavailable&channel=mobile_app");
    expect(el.textContent).toContain("Recorded signal: Issuer unavailable");
    expect(el.querySelector<HTMLSelectElement>("#attempts-failure-code")?.value).toBe("issuer_unavailable");
    expect(el.querySelector("a[data-export=attempts]")?.getAttribute("href")).toBe(
      "/api/reports/attempts.csv?period=last_7_days&outcome=failed&failure_code=issuer_unavailable&channel=mobile_app&sort=created_at&dir=desc",
    );
  });

  it("choosing a recorded signal also narrows to failed attempts", async () => {
    const { calls } = mockFetch(withSignals);
    page = await renderPage(<PaymentsPage />, "/payments?tab=attempts");
    await flush();
    await setValue(page.container.querySelector("#attempts-failure-code"), "do_not_honor");
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/attempts?")).at(-1)?.url).toContain("outcome=failed&failure_code=do_not_honor");
  });

  it("offers a way back to Payment Health with the original scope, even after the filters change", async () => {
    mockFetch(withSignals);
    page = await renderPage(
      <PaymentsPage />,
      "/payments?period=custom&from=2026-10-01&to=2026-10-02&status=failed&channel=mobile_app&ph_period=custom&ph_from=2026-10-01&ph_to=2026-10-02&ph_channel=mobile_app",
    );
    await flush();
    const back = () => Array.from(page!.container.querySelectorAll("a")).find((a) => a.textContent === "Back to Payment Health");
    expect(back()?.getAttribute("href")).toBe("/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app");
    await setValue(page.container.querySelector("#payments-status"), "succeeded");
    await flush();
    expect(back()?.getAttribute("href")).toBe("/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app");
  });

  it("shows no back link when the visit did not start on Payment Health", async () => {
    mockFetch(withSignals);
    page = await renderPage(<PaymentsPage />, "/payments?status=failed");
    await flush();
    expect(page.container.textContent).not.toContain("Back to Payment Health");
  });
});
