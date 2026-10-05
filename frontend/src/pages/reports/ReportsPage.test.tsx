import { afterEach, describe, expect, it } from "vitest";
import { META } from "../../test/fixtures";
import { DANIEL, MAYA, SAM, mockFetch, type Handler } from "../../test/mockApi";
import { flush, renderPage, setValue, type Rendered } from "../../test/render";
import { ReportsPage } from "./ReportsPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

function handlerFor(session = MAYA): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: session };
    if (url === "/api/meta") return { status: 200, body: META };
    return undefined;
  };
}

function hrefs(el: Element): Record<string, string | null> {
  return Object.fromEntries(Array.from(el.querySelectorAll("a[data-report]")).map((a) => [a.getAttribute("data-report"), a.getAttribute("href")]));
}

describe("ReportsPage", () => {
  it("shows the two operational reports to an operations manager with download links that carry the filters", async () => {
    mockFetch(handlerFor());
    page = await renderPage(<ReportsPage />, "/reports");
    await flush();
    const el = page.container;
    expect(hrefs(el)).toEqual({ payments: "/api/reports/payments.csv?period=last_7_days", attempts: "/api/reports/attempts.csv?period=last_7_days" });
    await setValue(el.querySelector("#pr-status"), "failed");
    await flush();
    await setValue(el.querySelector("#pr-period-preset"), "last_30_days");
    await flush();
    await setValue(el.querySelector("#ar-outcome"), "failed");
    await flush();
    expect(hrefs(el)).toEqual({
      payments: "/api/reports/payments.csv?period=last_30_days&status=failed",
      attempts: "/api/reports/attempts.csv?period=last_7_days&outcome=failed",
    });
    expect(el.textContent).not.toContain("Payout reconciliation");
  });

  it("shows all four reports to a finance manager", async () => {
    mockFetch(handlerFor(DANIEL));
    page = await renderPage(<ReportsPage />, "/reports?po_status=paid&po_from=2026-09-01&po_to=2026-09-30");
    await flush();
    const links = hrefs(page.container);
    expect(Object.keys(links)).toEqual(["payments", "attempts", "payouts", "refunds"]);
    expect(links["payouts"]).toBe("/api/reports/payouts.csv?status=paid&from=2026-09-01&to=2026-09-30");
    expect(links["refunds"]).toBe("/api/reports/refunds.csv?period=last_7_days");
  });

  it("shows the forbidden state to a role with no export permission", async () => {
    mockFetch(handlerFor(SAM));
    page = await renderPage(<ReportsPage />, "/reports");
    await flush();
    expect(page.container.textContent).toContain("Your role does not include this section");
    expect(page.container.querySelectorAll("a[data-report]").length).toBe(0);
  });
});
