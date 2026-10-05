import { afterEach, describe, expect, it } from "vitest";
import type { PayoutDetail, PayoutListResponse } from "../../api/payouts-types";
import { DANIEL, JORDAN, mockFetch, type Handler } from "../../test/mockApi";
import { flush, renderPage, type Rendered } from "../../test/render";
import { PayoutDetailPage } from "../payout-detail/PayoutDetailPage";
import { PayoutsPage } from "./PayoutsPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

const LIST: PayoutListResponse = {
  items: [
    {
      id: "po_transit00000001",
      status: "in_transit",
      status_label: "In transit",
      amount_cents: 9817797,
      currency: "USD",
      cutoff_at: "2026-10-05T05:00:00Z",
      payout_date: "2026-10-05",
      sent_at: "2026-10-05T11:00:00Z",
      expected_arrival_date: "2026-10-06",
      paid_at: null,
      destination: "Alder & Loom, Operating account •••• 4821, external bank account, demo record",
    },
    {
      id: "po_paid0000000001",
      status: "paid",
      status_label: "Paid",
      amount_cents: 2529447,
      currency: "USD",
      cutoff_at: "2026-10-02T05:00:00Z",
      payout_date: "2026-10-02",
      sent_at: "2026-10-02T11:00:00Z",
      expected_arrival_date: "2026-10-05",
      paid_at: "2026-10-05T14:00:00Z",
      destination: "Alder & Loom, Operating account •••• 4821, external bank account, demo record",
    },
  ],
  page: 1,
  page_size: 25,
  total: 2,
  summary: {
    as_of: "2026-10-05T14:12:00Z",
    available_cents: 296450,
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
    destination: "Alder & Loom, Operating account •••• 4821, external bank account, demo record",
  },
};

const DETAIL: PayoutDetail = {
  ...LIST.items[1]!,
  destination_label: "Operating account",
  destination_last4: "4821",
  destination_kind: "external bank account",
  buckets: { collections_cents: 2600000, fees_cents: -50553, refunds_cents: -20000, disputes_cents: 0, adjustments_cents: 0 },
  movement_total_cents: 2529447,
  movement_count: 3,
  reconciled: true,
  movements: [
    { id: "bm_1", type: "charge", type_label: "Collection", amount_cents: 2600000, currency: "USD", description: "Payment AL-12039", posted_at: "2026-09-30T06:42:24Z", available_at: "2026-10-02T06:42:24Z", payment_id: "pay_1", order_reference: "AL-12039", customer_name: "Wren Romero", refund_id: null, dispute_id: null },
    { id: "bm_2", type: "fee", type_label: "Fee", amount_cents: -50553, currency: "USD", description: "Fee for AL-12039", posted_at: "2026-09-30T06:42:24Z", available_at: "2026-10-02T06:42:24Z", payment_id: "pay_1", order_reference: "AL-12039", customer_name: "Wren Romero", refund_id: null, dispute_id: null },
    { id: "bm_3", type: "refund", type_label: "Refund", amount_cents: -20000, currency: "USD", description: "Refund for AL-11990", posted_at: "2026-10-01T12:00:00Z", available_at: "2026-10-01T12:00:00Z", payment_id: "pay_2", order_reference: "AL-11990", customer_name: null, refund_id: "ref_1", dispute_id: null },
  ],
};

function handlerFor(session = DANIEL): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: session };
    if (url.startsWith("/api/payouts?")) return { status: 200, body: LIST };
    if (url === "/api/payouts/po_paid0000000001") return { status: 200, body: DETAIL };
    return undefined;
  };
}

describe("PayoutsPage", () => {
  it("shows funds available as an estimate as of the clock, the next payout, and the list", async () => {
    mockFetch(handlerFor());
    page = await renderPage(<PayoutsPage />, "/payouts");
    await flush();
    const text = page.container.textContent ?? "";
    expect(text).toContain("Funds available for payout");
    expect(text).toContain("$2,964.50");
    expect(text).toContain("As of Oct 5, 2026, 9:12:00 AM CDT");
    expect(text).toContain("Not a bank balance");
    expect(text).not.toContain("Available balance");
    expect(text).toContain("Next payout · Tue, Oct 6");
    expect(text).toContain("$62,961.04");
    const rows = page.container.querySelectorAll("tbody tr");
    expect(rows.length).toBe(2);
    expect(rows[0]?.textContent).toContain("In transit");
    expect(rows[0]?.textContent).toContain("Expected Oct 6, 2026");
    expect(rows[1]?.textContent).toContain("Paid");
    expect(rows[1]?.textContent).toContain("$25,294.47");
  });
});

describe("PayoutDetailPage", () => {
  it("reconciles the buckets to the payout total and lists movements with payment links", async () => {
    mockFetch(handlerFor());
    page = await renderPage(<PayoutDetailPage />, "/payouts/po_paid0000000001", "/payouts/:payoutId");
    await flush();
    const el = page.container;
    expect(el.textContent).toContain("Reconciled to the cent");
    const recon = Array.from(el.querySelectorAll(".recon-table tr")).map((tr) => tr.textContent);
    expect(recon).toEqual(["Collections$26,000.00", "Fees−$505.53", "Refunds−$200.00", "Disputes$0.00", "Adjustments$0.00", "Payout total$25,294.47"]);
    expect(el.querySelectorAll("tbody tr").length).toBe(6 + 3);
    expect(el.querySelector("a[href='/payments/pay_1']")?.textContent).toBe("AL-12039");
    const download = el.querySelector("a[download]");
    expect(download?.getAttribute("href")).toBe("/api/payouts/po_paid0000000001/export.csv");
  });

  it("hides the CSV download for a role without reports:financial", async () => {
    mockFetch(handlerFor(JORDAN));
    page = await renderPage(<PayoutDetailPage />, "/payouts/po_paid0000000001", "/payouts/:payoutId");
    await flush();
    expect(page.container.querySelector("a[download]")).toBeNull();
    expect(page.container.textContent).toContain("Reconciled to the cent");
  });
});
