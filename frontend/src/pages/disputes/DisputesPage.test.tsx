import { afterEach, describe, expect, it } from "vitest";
import type { DisputeDetail, DisputeListResponse } from "../../api/disputes-types";
import { META } from "../../test/fixtures";
import { DANIEL, MAYA, mockFetch, type Handler } from "../../test/mockApi";
import { flush, renderPage, setValue, type Rendered } from "../../test/render";
import { DisputeDetailPage } from "../dispute-detail/DisputeDetailPage";
import { deadlineText } from "./Deadline";
import { DisputesPage } from "./DisputesPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

const OPEN = {
  id: "dp_open0000000001",
  status: "needs_response" as const,
  status_label: "Needs response",
  reason: "product_not_received",
  reason_label: "Product not received",
  amount_cents: 154350,
  currency: "USD",
  opened_at: "2026-09-23T13:04:00Z",
  evidence_due_at: "2026-10-07T13:04:00Z",
  responded_at: null,
  resolved_at: null,
  payment: { id: "pay_disputed000001", order_reference: "AL-10831", amount_cents: 154350, currency: "USD", created_at: "2026-09-10T16:20:00Z", customer: { id: "cus_1", full_name: "Rowan Diaz", email: "rowan.diaz@example.com", reference: "AL-C-0200" } },
};
const LIST: DisputeListResponse = {
  items: [
    OPEN,
    { ...OPEN, id: "dp_won00000000001", status: "won", status_label: "Won", responded_at: "2026-09-12T12:00:00Z", resolved_at: "2026-09-26T14:00:00Z", amount_cents: 12569, payment: { ...OPEN.payment, id: "pay_won", order_reference: "AL-10124", customer: null } },
  ],
  page: 1,
  page_size: 25,
  total: 2,
};
const DETAIL: DisputeDetail = {
  ...OPEN,
  history: [
    { kind: "order_received", at: "2026-09-10T16:20:00Z", title: "Payment received", detail: "AL-10831 · $1,543.50", upcoming: false, amount_cents: 154350, ref_id: "pay_disputed000001" },
    { kind: "dispute_opened", at: "2026-09-23T13:04:00Z", title: "Dispute opened", detail: "Reason given: Product not received", upcoming: false, amount_cents: null, ref_id: "dp_open0000000001" },
    { kind: "funds_withheld", at: "2026-09-23T13:04:00Z", title: "Disputed amount withheld", detail: "Reversed from the balance while the case is open", upcoming: false, amount_cents: -154350, ref_id: "bm_1" },
    { kind: "dispute_fee", at: "2026-09-23T13:04:00Z", title: "Dispute fee charged", detail: "Charged by the card network for the case", upcoming: false, amount_cents: -1500, ref_id: "bm_2" },
    { kind: "dispute_evidence_due", at: "2026-10-07T13:04:00Z", title: "Evidence due", detail: "Respond before this deadline", upcoming: true, amount_cents: null, ref_id: "dp_open0000000001" },
  ],
  notes: [{ id: "evt_1", body: "Asked the carrier for proof of delivery.", created_at: "2026-09-24T15:00:00Z", actor: { id: "usr_maya0000000001", full_name: "Maya Chen" } }],
};

function handlerFor(session = MAYA): Handler {
  return (url, init) => {
    if (url === "/api/session") return { status: 200, body: session };
    if (url === "/api/meta") return { status: 200, body: META };
    if (url.startsWith("/api/disputes?")) return { status: 200, body: LIST };
    if (url === "/api/disputes/dp_open0000000001") return { status: 200, body: DETAIL };
    if (url === "/api/disputes/dp_open0000000001/notes" && init?.method === "POST") return { status: 201, body: { ...DETAIL.notes[0], id: "evt_2", body: "New note" } };
    return undefined;
  };
}

describe("deadlineText", () => {
  it("counts whole Chicago days from the reporting clock", () => {
    expect(deadlineText("2026-10-07T13:04:00Z", "2026-10-05T14:12:00Z")).toBe("Due in 2 days");
    expect(deadlineText("2026-10-06T04:30:00Z", "2026-10-05T14:12:00Z")).toBe("Due today"); // 11:30 PM CDT on Oct 5
    expect(deadlineText("2026-10-06T05:30:00Z", "2026-10-05T14:12:00Z")).toBe("Due in 1 day");
    expect(deadlineText("2026-10-01T13:04:00Z", "2026-10-05T14:12:00Z")).toBe("Overdue by 4 days");
  });
});

describe("DisputesPage", () => {
  it("lists the queue with the deadline against the clock and filters in the URL", async () => {
    const { calls } = mockFetch(handlerFor());
    page = await renderPage(<DisputesPage />, "/disputes");
    await flush();
    const el = page.container;
    expect(calls.find((c) => c.url.startsWith("/api/disputes?"))?.url).toBe("/api/disputes?sort=queue&dir=asc&page=1&page_size=25");
    const rows = el.querySelectorAll("tbody tr");
    expect(rows.length).toBe(2);
    expect(rows[0]?.textContent).toContain("Needs response");
    expect(rows[0]?.textContent).toContain("Due in 2 days");
    expect(rows[0]?.textContent).toContain("Oct 7, 2026");
    expect(rows[0]?.textContent).toContain("$1,543.50");
    expect(rows[1]?.textContent).toContain("Resolved Sep 26, 2026");
    expect(rows[1]?.textContent).toContain("Guest");
    expect(el.querySelector("a[href='/payments/pay_disputed000001']")).not.toBeNull();
    await setValue(el.querySelector("#disputes-status"), "won");
    await flush();
    expect(calls.filter((c) => c.url.startsWith("/api/disputes?")).at(-1)?.url).toContain("status=won");
    expect(el.textContent).toContain("Status: Won");
  });
});

describe("DisputeDetailPage", () => {
  it("shows the case history, the deadline, the payment link and the note composer for a role with notes:write", async () => {
    mockFetch(handlerFor());
    page = await renderPage(<DisputeDetailPage />, "/disputes/dp_open0000000001", "/disputes/:disputeId");
    await flush();
    const el = page.container;
    expect(el.querySelector("h1")?.textContent).toContain("Dispute on AL-10831");
    expect(el.textContent).toContain("Due in 2 days");
    expect(el.querySelectorAll(".timeline-item").length).toBe(5);
    expect(el.querySelector(".timeline-item.upcoming")?.textContent).toContain("Evidence due");
    expect(el.textContent).toContain("−$1,543.50");
    expect(el.textContent).toContain("−$15.00");
    expect(el.querySelector("a[href='/payments/pay_disputed000001']")).not.toBeNull();
    expect(el.querySelector("a[href='/customers/cus_1']")).not.toBeNull();
    expect(el.textContent).toContain("Asked the carrier for proof of delivery.");
    expect(el.querySelector("#note-body")).not.toBeNull();
    expect(Array.from(el.querySelectorAll("button")).map((b) => b.textContent)).toEqual(["Add note"]);
  });

  it("is read-only for a role without notes:write and never offers resolution actions", async () => {
    mockFetch(handlerFor(DANIEL));
    page = await renderPage(<DisputeDetailPage />, "/disputes/dp_open0000000001", "/disputes/:disputeId");
    await flush();
    const el = page.container;
    expect(el.querySelector("#note-body")).toBeNull();
    expect(el.textContent).toContain("Notes are read-only for your role.");
    expect(el.querySelectorAll("button").length).toBe(0);
    expect(el.querySelector("a[href='/customers/cus_1']")).toBeNull(); // finance has no customers:read
  });
});
