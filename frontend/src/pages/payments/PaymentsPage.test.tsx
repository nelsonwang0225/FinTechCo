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

  describe("opened from Payment Health", () => {
    const backLink = (el: HTMLElement) => Array.from(el.querySelectorAll("a")).find((a) => a.textContent?.includes("Back to Payment Health")) ?? null;
    const noScopeKeys = (url: string) => Array.from(new URLSearchParams(url.slice(url.indexOf("?"))).keys()).filter((k) => k.startsWith("ph_"));

    it("links back to the original custom scope, keeps ph_ keys out of the API and survives a filter change", async () => {
      const { calls } = mockFetch(handler);
      page = await renderPage(
        <PaymentsPage />,
        "/payments?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app&status=failed&ph_period=custom&ph_from=2026-10-01&ph_to=2026-10-02&ph_channel=mobile_app",
      );
      await flush();
      const el = page.container;
      expect(backLink(el)?.getAttribute("href")).toBe("/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app");
      const listCall = calls.find((c) => c.url.startsWith("/api/payments?"));
      expect(listCall?.url).toContain("period=custom&from=2026-10-01&to=2026-10-02");
      expect(listCall?.url).toContain("status=failed");
      expect(listCall?.url).toContain("channel=mobile_app");
      expect(noScopeKeys(listCall?.url ?? "")).toEqual([]);
      expect(noScopeKeys(el.querySelector("a[data-export=payments]")?.getAttribute("href") ?? "")).toEqual([]);

      await setValue(el.querySelector("#payments-status"), "succeeded");
      await flush();
      const last = calls.filter((c) => c.url.startsWith("/api/payments?")).at(-1);
      expect(last?.url).toContain("status=succeeded");
      expect(noScopeKeys(last?.url ?? "")).toEqual([]);
      expect(backLink(el)?.getAttribute("href")).toBe("/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app");
    });

    it("links back to a preset scope with no channel", async () => {
      mockFetch(handler);
      page = await renderPage(<PaymentsPage />, "/payments?period=last_7_days&status=failed&ph_period=last_7_days");
      await flush();
      expect(backLink(page.container)?.getAttribute("href")).toBe("/payment-health?period=last_7_days");
    });

    it("shows no back link without the ph_ keys", async () => {
      mockFetch(handler);
      page = await renderPage(<PaymentsPage />, "/payments?period=last_7_days&status=failed");
      await flush();
      expect(backLink(page.container)).toBeNull();
    });

    it("filters the attempts tab by outcome and recorded signal, with the chip, the export and the back link", async () => {
      const { calls } = mockFetch(handler);
      page = await renderPage(<PaymentsPage />, "/payments?tab=attempts&period=last_7_days&outcome=failed&failure_code=issuer_unavailable&ph_period=last_7_days");
      await flush();
      const el = page.container;
      const listCall = calls.find((c) => c.url.startsWith("/api/attempts?"));
      expect(listCall?.url).toContain("outcome=failed");
      expect(listCall?.url).toContain("failure_code=issuer_unavailable");
      expect(noScopeKeys(listCall?.url ?? "")).toEqual([]);
      expect(el.textContent).toContain("Signal: Issuer unavailable");
      expect((el.querySelector("#attempts-failure-code") as HTMLSelectElement | null)?.value).toBe("issuer_unavailable");
      const exportHref = el.querySelector("a[data-export=attempts]")?.getAttribute("href") ?? "";
      expect(exportHref).toContain("failure_code=issuer_unavailable");
      expect(noScopeKeys(exportHref)).toEqual([]);
      expect(backLink(el)?.getAttribute("href")).toBe("/payment-health?period=last_7_days");
    });

    const OCT_SCOPE = "period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app";
    const OCT_BACK = "ph_period=custom&ph_from=2026-10-01&ph_to=2026-10-02&ph_channel=mobile_app";
    const OCT_PERIOD = { preset: "custom", label: "Custom", from_date: "2026-10-01", to_date: "2026-10-02", range_label: "Oct 1 – 2, 2026" };
    const unresolvedHandler: Handler = (url, init) => {
      if (url.startsWith("/api/payments?")) return { status: 200, body: { ...PAYMENTS, total: 12, total_amount_cents: 422811, period: OCT_PERIOD } };
      if (url.startsWith("/api/attempts?")) return { status: 200, body: { ...ATTEMPTS, total: 29, period: OCT_PERIOD } };
      return handler(url, init);
    };
    const contextBar = (el: HTMLElement) => el.querySelector("section[aria-label='Opened from Payment Health']");

    it("shows the context bar on the unresolved list with the count and value that were clicked, and exports exactly that set", async () => {
      mockFetch(unresolvedHandler);
      page = await renderPage(<PaymentsPage />, `/payments?${OCT_SCOPE}&status=failed&${OCT_BACK}`);
      await flush();
      const el = page.container;
      expect(contextBar(el)?.querySelector(".health-context-scope")?.textContent).toBe("From Payment Health · Oct 1 – 2, 2026 · Mobile app · Failed");
      expect(contextBar(el)?.querySelector(".health-context-result")?.textContent).toBe("12 payments · $4,228.11");
      // The way back lives in the context bar.
      expect(backLink(el)?.closest("section")).toBe(contextBar(el));
      // Maya (reports:operational) can export, and the export carries exactly the list's filters.
      expect(el.querySelector("a[data-export=payments]")?.getAttribute("href")).toBe(
        "/api/reports/payments.csv?period=custom&from=2026-10-01&to=2026-10-02&status=failed&channel=mobile_app&sort=created_at&dir=desc",
      );
    });

    it("opens a payment with the list's query, so detail can link back to the list and to Payment Health", async () => {
      mockFetch(unresolvedHandler);
      page = await renderPage(<PaymentsPage />, `/payments?${OCT_SCOPE}&status=failed&${OCT_BACK}`);
      await flush();
      const link = page.container.querySelector("tbody tr a.row-link");
      expect(link?.getAttribute("href")).toBe(`/payments/pay_anchor00000001?${OCT_SCOPE}&status=failed&${OCT_BACK}`);
    });

    it("keeps plain detail links and no context bar outside the flow", async () => {
      mockFetch(handler);
      page = await renderPage(<PaymentsPage />, "/payments?period=last_7_days&status=failed");
      await flush();
      expect(contextBar(page.container)).toBeNull();
      expect(page.container.querySelector("tbody tr a.row-link")?.getAttribute("href")).toBe("/payments/pay_anchor00000001");
    });

    it("describes a signal drill-down on the attempts tab with its failed-attempt count", async () => {
      mockFetch(unresolvedHandler);
      page = await renderPage(<PaymentsPage />, `/payments?tab=attempts&${OCT_SCOPE}&outcome=failed&failure_code=issuer_unavailable&${OCT_BACK}`);
      await flush();
      const el = page.container;
      expect(contextBar(el)?.querySelector(".health-context-scope")?.textContent).toBe("From Payment Health · Oct 1 – 2, 2026 · Mobile app · Failed · Issuer unavailable");
      expect(contextBar(el)?.querySelector(".health-context-result")?.textContent).toBe("29 failed attempts");
      expect(el.querySelector("tbody tr a.row-link")?.getAttribute("href")).toContain(`?tab=attempts&${OCT_SCOPE}&outcome=failed&failure_code=issuer_unavailable&${OCT_BACK}`);
    });

    it("puts a chosen signal in the URL and the request without forcing an outcome", async () => {
      const { calls } = mockFetch(handler);
      page = await renderPage(<PaymentsPage />, "/payments?tab=attempts");
      await flush();
      await setValue(page.container.querySelector("#attempts-failure-code"), "do_not_honor");
      await flush();
      const last = calls.filter((c) => c.url.startsWith("/api/attempts?")).at(-1);
      expect(last?.url).toContain("failure_code=do_not_honor");
      expect(last?.url).not.toContain("outcome=");
      expect(page.container.textContent).toContain("Signal: Do not honor");
    });
  });
});
