import { afterEach, describe, expect, it } from "vitest";
import type { CustomerDetail, CustomerListResponse } from "../../api/customers-types";
import { PAYMENTS } from "../../test/fixtures";
import { MAYA, mockFetch, type Handler } from "../../test/mockApi";
import { flush, renderPage, setValue, type Rendered } from "../../test/render";
import { CustomerDetailPage } from "../customer-detail/CustomerDetailPage";
import { CustomersPage } from "./CustomersPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

const LIST: CustomerListResponse = {
  items: [
    { id: "cus_taylor00000001", reference: "AL-C-0101", full_name: "Taylor Reed", email: "taylor.reed@example.com", created_at: "2025-03-14T01:59:00Z", first_payment_at: "2026-09-06T15:08:31Z", last_activity_at: "2026-10-05T10:35:26Z" },
    { id: "cus_ingrid00000001", reference: "AL-C-0030", full_name: "Ingrid Kim", email: "ingrid.kim@example.com", created_at: "2025-03-14T01:59:00Z", first_payment_at: null, last_activity_at: null },
  ],
  page: 1,
  page_size: 25,
  total: 2,
};

const DETAIL: CustomerDetail = {
  ...LIST.items[0]!,
  payments: [PAYMENTS.items[0]!],
  refunds: [
    { id: "ref_1", amount_cents: 4800, currency: "USD", reason: "price_adjustment", reason_label: "Price adjustment", status: "succeeded", status_label: "Succeeded", created_at: "2026-09-24T15:02:11Z", completed_at: "2026-09-24T15:02:11Z", payment_id: "pay_anchor00000001", order_reference: "AL-11404" },
  ],
};

const handler: Handler = (url) => {
  if (url === "/api/session") return { status: 200, body: MAYA };
  if (url.startsWith("/api/customers?")) return { status: 200, body: LIST };
  if (url === "/api/customers/cus_taylor00000001") return { status: 200, body: DETAIL };
  return undefined;
};

describe("CustomersPage", () => {
  it("lists customers with derived activity and puts the search in the URL", async () => {
    const { calls } = mockFetch(handler);
    page = await renderPage(<CustomersPage />, "/customers");
    await flush();
    const el = page.container;
    expect(calls.find((c) => c.url.startsWith("/api/customers?"))?.url).toBe("/api/customers?sort=last_activity_at&dir=desc&page=1&page_size=25");
    const rows = el.querySelectorAll("tbody tr");
    expect(rows.length).toBe(2);
    expect(rows[0]?.textContent).toContain("Taylor Reed");
    expect(rows[0]?.textContent).toContain("taylor.reed@example.com");
    expect(rows[0]?.textContent).toContain("AL-C-0101");
    expect(rows[1]?.textContent).toContain("—"); // no activity yet renders as a dash, never a fake date
    expect(el.querySelector("a[href='/customers/cus_taylor00000001']")).not.toBeNull();
    await setValue(el.querySelector("#customers-search"), "ingrid");
    await new Promise((r) => setTimeout(r, 400));
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/customers?")).at(-1)?.url).toContain("q=ingrid");
  });
});

describe("CustomerDetailPage", () => {
  it("shows the customer's payments and refunds with links to each payment", async () => {
    mockFetch(handler);
    page = await renderPage(<CustomerDetailPage />, "/customers/cus_taylor00000001", "/customers/:customerId");
    await flush();
    const el = page.container;
    expect(el.querySelector("h1")?.textContent).toBe("Taylor Reed");
    expect(el.textContent).toContain("AL-C-0101");
    expect(el.textContent).toContain("Recent activity");
    expect(el.querySelectorAll("a[href='/payments/pay_anchor00000001']").length).toBe(2);
    expect(el.textContent).toContain("Partially refunded");
    expect(el.textContent).toContain("Price adjustment");
    expect(el.textContent).toContain("−$48.00");
  });

  it("renders the not-found state for a customer outside the business", async () => {
    mockFetch((url) => (url === "/api/session" ? { status: 200, body: MAYA } : undefined));
    page = await renderPage(<CustomerDetailPage />, "/customers/cus_elsewhere00001", "/customers/:customerId");
    await flush();
    expect(page.container.textContent).toContain("not in this business");
  });
});
