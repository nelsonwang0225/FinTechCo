import { afterEach, describe, expect, it } from "vitest";
import { ANCHOR_DETAIL } from "../../test/fixtures";
import { MAYA, PRIYA, mockFetch, type Handler } from "../../test/mockApi";
import { click, flush, renderPage, setValue, type Rendered } from "../../test/render";
import { PaymentDetailPage } from "./PaymentDetailPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

function handlerFor(session = MAYA): { handler: Handler; notes: string[] } {
  const notes: string[] = [];
  const handler: Handler = (url, init) => {
    if (url === "/api/session") return { status: 200, body: session };
    if (url === "/api/payments/pay_anchor00000001" && (init?.method ?? "GET") === "GET") {
      const extra = notes.map((body, i) => ({ id: `evt_new${i}`, body, created_at: "2026-10-05T14:30:00Z", actor: { id: session.user.id, full_name: session.user.full_name } }));
      return { status: 200, body: { ...ANCHOR_DETAIL, notes: [...ANCHOR_DETAIL.notes, ...extra] } };
    }
    if (url === "/api/payments/pay_anchor00000001/notes" && init?.method === "POST") {
      const body = JSON.parse(String(init.body)) as { body: string };
      notes.push(body.body);
      return { status: 201, body: { id: `evt_new${notes.length - 1}`, body: body.body, created_at: "2026-10-05T14:30:00Z", actor: { id: session.user.id, full_name: session.user.full_name } } };
    }
    if (url === "/api/payments/pay_missing0000001") return { status: 404, body: { error: { code: "not_found", message: "That payment is not in this business." } } };
    return undefined;
  };
  return { handler, notes };
}

describe("PaymentDetailPage", () => {
  it("renders the header, summary, timeline in order, attempts and refunds", async () => {
    mockFetch(handlerFor().handler);
    page = await renderPage(<PaymentDetailPage />, "/payments/pay_anchor00000001", "/payments/:paymentId");
    await flush();
    const el = page.container;
    expect(el.querySelector("h1")?.textContent).toContain("AL-11404");
    expect(el.querySelector("h1")?.textContent).toContain("Partially refunded");
    expect(el.textContent).toContain("$343.98");
    expect(el.textContent).toContain("Net $295.98 after refunds");
    expect(el.textContent).toContain("Taylor Reed");
    expect(el.textContent).toContain("Mastercard •••• 8812");
    const titles = Array.from(el.querySelectorAll(".timeline-title")).map((t) => t.textContent);
    expect(titles).toEqual([
      "Order received",
      "Attempt 1 declined",
      "Attempt 2 succeeded",
      "Funds available for payout",
      "Included in payout",
      "Refund of $48.00 completed",
      "Note by Maya Chen",
      "Payout paid",
    ]);
    expect(el.textContent).toContain("Insufficient funds");
    expect(el.textContent).toContain("Price adjustment");
    expect(el.textContent).toContain("−$48.00");
    expect(el.textContent).not.toContain("Issue refund");
    // Maya cannot read payouts, so the payout is text, not a link; she can read customers, so the customer is a link.
    expect(el.querySelector("a[href='/payouts/po_anchor000000001']")).toBeNull();
    expect(el.querySelector("a[href='/customers/cus_taylor00000001']")).not.toBeNull();
  });

  it("saves a note for a role with notes:write and shows it afterwards", async () => {
    const { handler, notes } = handlerFor();
    const { calls } = mockFetch(handler);
    page = await renderPage(<PaymentDetailPage />, "/payments/pay_anchor00000001", "/payments/:paymentId");
    await flush();
    const el = page.container;
    const button = Array.from(el.querySelectorAll("button")).find((b) => b.textContent === "Add note");
    expect(button?.disabled).toBe(true);
    await setValue(el.querySelector("#note-body"), "  Shopper confirmed delivery.  ");
    expect(button?.disabled).toBe(false);
    await click(button ?? null);
    await flush();
    await flush();
    expect(notes).toEqual(["Shopper confirmed delivery."]);
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toEqual({ body: "Shopper confirmed delivery." });
    expect(el.textContent).toContain("Note saved.");
    expect(el.textContent).toContain("Shopper confirmed delivery.");
    expect((el.querySelector("#note-body") as HTMLTextAreaElement).value).toBe("");
  });

  it("shows a read-only notice for a role without notes:write", async () => {
    const analyst = { ...PRIYA, permissions: PRIYA.permissions.filter((p) => p !== "notes:write") };
    mockFetch(handlerFor(analyst).handler);
    page = await renderPage(<PaymentDetailPage />, "/payments/pay_anchor00000001", "/payments/:paymentId");
    await flush();
    expect(page.container.querySelector("#note-body")).toBeNull();
    expect(page.container.textContent).toContain("Notes are read-only for your role.");
  });

  it("renders the not-found state for an id outside this business", async () => {
    mockFetch(handlerFor().handler);
    page = await renderPage(<PaymentDetailPage />, "/payments/pay_missing0000001", "/payments/:paymentId");
    await flush();
    expect(page.container.textContent).toContain("That payment is not in this business");
  });
});
