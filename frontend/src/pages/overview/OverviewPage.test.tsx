import { afterEach, describe, expect, it } from "vitest";
import type { Overview } from "../../api/overview-types";
import { META, PAYMENTS, PERIOD } from "../../test/fixtures";
import { JORDAN, MAYA, mockFetch, type Handler } from "../../test/mockApi";
import { flush, renderPage, setValue, type Rendered } from "../../test/render";
import { OverviewPage } from "./OverviewPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

const OVERVIEW: Overview = {
  greeting: { salutation: "Good morning", first_name: "Maya", merchant_name: "Alder & Loom", as_of: "2026-10-05T14:12:00Z" },
  period: PERIOD,
  tiles: {
    collected_cents: 20666537,
    refunds_cents: 1141394,
    funds_available_cents: 296450,
    pending_cents: 6296104,
    currency: "USD",
    next_payout: {
      cutoff_at: "2026-10-06T05:00:00Z",
      payout_date: "2026-10-06",
      amount_cents: 296450,
      currency: "USD",
      schedule: "daily",
      schedule_label: "Every business day",
      note: "Estimate as of now: the funds currently available for payout. Not a bank balance.",
    },
  },
  chart: {
    title: "Collected by day",
    points: [
      { day: "2026-09-29", amount_cents: 2670484 },
      { day: "2026-09-30", amount_cents: 4155882 },
      { day: "2026-10-01", amount_cents: 3220087 },
      { day: "2026-10-02", amount_cents: 3798787 },
      { day: "2026-10-03", amount_cents: 3903190 },
      { day: "2026-10-04", amount_cents: 2729357 },
      { day: "2026-10-05", amount_cents: 188750 },
    ],
    total_cents: 20666537,
    currency: "USD",
  },
  recent_payments: PAYMENTS.items,
  upcoming_payout: {
    cutoff_at: "2026-10-06T05:00:00Z",
    payout_date: "2026-10-06",
    amount_cents: 296450,
    currency: "USD",
    schedule: "daily",
    schedule_label: "Every business day",
    destination: "Alder & Loom, Operating account •••• 4821, external bank account, demo record",
    note: "Estimate as of now: the funds currently available for payout. Not a bank balance.",
    buckets: { collections_cents: 336042, fees_cents: -9955, refunds_cents: -29637, disputes_cents: 0, adjustments_cents: 0 },
  },
  attention: [
    {
      kind: "dispute_deadline",
      title: "Dispute on AL-10831 needs a response",
      detail: "$1,543.50 is held until the case is decided.",
      at: "2026-10-07T13:04:00Z",
      at_label: "Evidence due",
      amount_cents: 154350,
      currency: "USD",
      link: { kind: "dispute", id: "dp_y57y6y6bshwq7b", permission: "disputes:read" },
    },
    {
      kind: "payout_in_transit",
      title: "Payout of $98,177.97 is on its way",
      detail: "Expected to arrive Tuesday, Oct 6.",
      at: "2026-10-05T11:00:00Z",
      at_label: "Sent",
      amount_cents: 9817797,
      currency: "USD",
      link: { kind: "payout", id: "po_dnudywpeagoxrl", permission: "payouts:read" },
    },
    {
      kind: "refund_pending",
      title: "Refund of $48.51 on AL-12404 is pending",
      detail: "It will post to the ledger once the processor completes it.",
      at: "2026-10-05T03:55:00Z",
      at_label: "Requested",
      amount_cents: 4851,
      currency: "USD",
      link: { kind: "payment", id: "pay_ley45cy6ymthws", permission: "payments:read" },
    },
  ],
};

function handlerFor(session = MAYA): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: session };
    if (url === "/api/meta") return { status: 200, body: META };
    if (url.startsWith("/api/overview")) return { status: 200, body: OVERVIEW };
    return undefined;
  };
}

describe("OverviewPage", () => {
  it("greets from the reporting clock and shows the four tiles with period and as-of labels", async () => {
    const { calls } = mockFetch(handlerFor());
    page = await renderPage(<OverviewPage />, "/overview");
    await flush();
    const text = page.container.textContent ?? "";
    expect(calls.find((c) => c.url.startsWith("/api/overview"))?.url).toBe("/api/overview?period=last_7_days");
    expect(page.container.querySelector("h1")?.textContent).toBe("Good morning, Maya");
    expect(text).toContain("Alder & Loom · As of Oct 5, 2026, 9:12:00 AM CDT");
    expect(text).toContain("Gross collected$206,665.37Last 7 days · Sep 29 – Oct 5, 2026");
    expect(text).toContain("Refunds processed$11,413.94Last 7 days · Sep 29 – Oct 5, 2026");
    expect(text).toContain("Funds available for payout$2,964.50As of Oct 5, 2026, 9:12:00 AM CDT");
    expect(text).toContain("Next payout · Tue, Oct 6$2,964.50Estimate as of now");
    expect(text).toContain("Not a bank balance");
  });

  it("draws the collected-volume chart from the daily series without links", async () => {
    mockFetch(handlerFor());
    page = await renderPage(<OverviewPage />, "/overview");
    await flush();
    const chart = page.container.querySelector("svg[role=img]");
    expect(chart?.querySelector("title")?.textContent).toBe("Collected by day, Sep 29 – Oct 5, 2026");
    expect(chart?.querySelectorAll(".chart-bar").length).toBe(7);
    expect(chart?.querySelectorAll(".chart-bar")[1]?.querySelector("title")?.textContent).toBe("Sep 30: $41,558.82");
    expect(chart?.querySelectorAll("a").length).toBe(0);
    expect(page.container.textContent).toContain("$206,665.37 collected · Sep 29 – Oct 5, 2026");
  });

  it("lists recent payments, the upcoming payout itemisation and attention items with permission-gated links", async () => {
    mockFetch(handlerFor());
    page = await renderPage(<OverviewPage />, "/overview");
    await flush();
    const el = page.container;
    const rows = el.querySelectorAll("tbody tr");
    expect(rows.length).toBe(2);
    expect(rows[0]?.textContent).toContain("AL-11404");
    expect(el.querySelector("a[href='/payments/pay_anchor00000001']")).not.toBeNull();
    expect(el.textContent).toContain("Upcoming payout · Tue, Oct 6");
    expect(el.textContent).toContain("Collections$3,360.42");
    expect(el.textContent).toContain("Fees−$99.55");
    const items = el.querySelectorAll(".attention-item");
    expect(items.length).toBe(3);
    expect(items[0]?.querySelector("a")?.getAttribute("href")).toBe("/disputes/dp_y57y6y6bshwq7b");
    expect(items[0]?.textContent).toContain("Due in 2 days");
    // Maya has no payouts:read: the payout item is text, not a link, and the tile has no payouts link.
    expect(items[1]?.querySelector("a")).toBeNull();
    expect(items[1]?.textContent).toContain("Payout of $98,177.97 is on its way");
    expect(items[2]?.querySelector("a")?.getAttribute("href")).toBe("/payments/pay_ley45cy6ymthws");
    expect(el.querySelector("a[href='/payouts']")).toBeNull();
  });

  it("links to payouts for a role with payouts:read", async () => {
    mockFetch(handlerFor(JORDAN));
    page = await renderPage(<OverviewPage />, "/overview");
    await flush();
    const el = page.container;
    expect(el.querySelector("a[href='/payouts']")).not.toBeNull();
    expect(el.querySelectorAll(".attention-item")[1]?.querySelector("a")?.getAttribute("href")).toBe("/payouts/po_dnudywpeagoxrl");
  });

  it("keeps the period in the URL and refetches with it", async () => {
    const { calls } = mockFetch(handlerFor());
    page = await renderPage(<OverviewPage />, "/overview");
    await flush();
    await setValue(page.container.querySelector("#overview-period-preset"), "last_30_days");
    await flush();
    const last = calls.filter((c) => c.url.startsWith("/api/overview")).at(-1);
    expect(last?.url).toBe("/api/overview?period=last_30_days");
  });
});
