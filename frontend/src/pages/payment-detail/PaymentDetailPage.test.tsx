import { afterEach, describe, expect, it } from "vitest";
import type { AttemptItem, PaymentDetail } from "../../api/payments-types";
import { attemptChainSummary } from "../../lib/attemptChain";
import { ANCHOR_DETAIL } from "../../test/fixtures";
import { MAYA, PRIYA, mockFetch, type Handler } from "../../test/mockApi";
import { click, flush, renderPage, setValue, type Rendered } from "../../test/render";
import { PaymentDetailPage } from "./PaymentDetailPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

function handlerFor(session = MAYA, detail: PaymentDetail = ANCHOR_DETAIL): { handler: Handler; notes: string[] } {
  const notes: string[] = [];
  const handler: Handler = (url, init) => {
    if (url === "/api/session") return { status: 200, body: session };
    if (url === "/api/payments/pay_anchor00000001" && (init?.method ?? "GET") === "GET") {
      const extra = notes.map((body, i) => ({ id: `evt_new${i}`, body, created_at: "2026-10-05T14:30:00Z", actor: { id: session.user.id, full_name: session.user.full_name } }));
      return { status: 200, body: { ...detail, notes: [...detail.notes, ...extra] } };
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

  describe("inspecting one payment from Payment Health", () => {
    const SCOPE = "period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app&status=failed&ph_period=custom&ph_from=2026-10-01&ph_to=2026-10-02&ph_channel=mobile_app";
    const failed = (n: number, created: string): AttemptItem => ({
      id: `att_unresolved000${n}`,
      payment_id: "pay_anchor00000001",
      attempt_number: n,
      created_at: created,
      completed_at: created.replace(":00Z", ":02Z"),
      outcome: "failed",
      outcome_label: "Failed",
      failure_code: "issuer_unavailable",
      failure_message: "Issuer unavailable",
      method: { type: "card", card_brand: "visa", card_last4: "4242", wallet_type: null, label: "Visa •••• 4242" },
    });
    const UNRESOLVED: PaymentDetail = {
      ...ANCHOR_DETAIL,
      status: "failed",
      status_label: "Failed",
      channel: "mobile_app",
      channel_label: "Mobile app",
      refunded_cents: 0,
      net_cents: 0,
      succeeded_at: null,
      funds_available_at: null,
      payout: null,
      refunds: [],
      attempts: [failed(1, "2026-10-01T15:02:00Z"), failed(2, "2026-10-01T15:09:00Z")],
    };

    it("shows the attempt chain and its summary, and links back to the unresolved list and Payment Health", async () => {
      mockFetch(handlerFor(MAYA, UNRESOLVED).handler);
      page = await renderPage(<PaymentDetailPage />, `/payments/pay_anchor00000001?${SCOPE}`, "/payments/:paymentId");
      await flush();
      const el = page.container;
      const chain = el.querySelector("[aria-label='Attempt chain']");
      expect(chain?.querySelector(".attempt-chain-summary")?.textContent).toBe("2 failed attempts · no successful retry · recorded signal: Issuer unavailable");
      expect(Array.from(chain?.querySelectorAll(".attempt-chain-chip") ?? []).map((c) => c.textContent)).toEqual([
        "Attempt 1FailedIssuer unavailable",
        "Attempt 2FailedIssuer unavailable",
      ]);
      // The existing attempts table and timeline are still there.
      expect(el.querySelector("table[aria-label='Payment attempts'], table caption")).not.toBeNull();
      expect(el.querySelectorAll(".timeline-title").length).toBeGreaterThan(0);
      const links = Array.from(el.querySelectorAll(".breadcrumb a")).map((a) => [a.textContent, a.getAttribute("href")]);
      expect(links).toEqual([
        ["Back to unresolved payments", `/payments?${SCOPE}`],
        ["Back to Payment Health", "/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app"],
      ]);
    });

    it("saves an investigation note from the flow through the existing notes endpoint", async () => {
      const { handler, notes } = handlerFor(MAYA, UNRESOLVED);
      const { calls } = mockFetch(handler);
      page = await renderPage(<PaymentDetailPage />, `/payments/pay_anchor00000001?${SCOPE}`, "/payments/:paymentId");
      await flush();
      const el = page.container;
      const shortcut = Array.from(el.querySelectorAll("button")).find((b) => b.textContent === "Add investigation note");
      await click(shortcut ?? null);
      expect(document.activeElement?.id).toBe("note-body");
      const body = "Reviewed after mobile payment incident. Customer has not successfully retried.";
      await setValue(el.querySelector("#note-body"), body);
      await click(Array.from(el.querySelectorAll("button")).find((b) => b.textContent === "Add note") ?? null);
      await flush();
      await flush();
      expect(notes).toEqual([body]);
      expect(calls.find((c) => c.method === "POST")?.url).toBe("/api/payments/pay_anchor00000001/notes");
      expect(el.textContent).toContain(body);
      // The scope is still on the page after the save.
      expect(Array.from(el.querySelectorAll(".breadcrumb a")).map((a) => a.textContent)).toEqual(["Back to unresolved payments", "Back to Payment Health"]);
    });

    it("offers no note shortcut to a role without notes:write, and keeps the plain Payments link outside the flow", async () => {
      const analyst = { ...MAYA, permissions: MAYA.permissions.filter((p) => p !== "notes:write") };
      mockFetch(handlerFor(analyst, UNRESOLVED).handler);
      page = await renderPage(<PaymentDetailPage />, `/payments/pay_anchor00000001?${SCOPE}`, "/payments/:paymentId");
      await flush();
      expect(Array.from(page.container.querySelectorAll("button")).some((b) => b.textContent === "Add investigation note")).toBe(false);
      page.unmount();
      mockFetch(handlerFor().handler);
      page = await renderPage(<PaymentDetailPage />, "/payments/pay_anchor00000001", "/payments/:paymentId");
      await flush();
      expect(Array.from(page.container.querySelectorAll(".breadcrumb a")).map((a) => [a.textContent, a.getAttribute("href")])).toEqual([["Payments", "/payments"]]);
      // The summary line shows for every payment: the anchor failed once, then succeeded about three minutes later.
      expect(page.container.querySelector(".attempt-chain-summary")?.textContent).toBe("1 failed attempt · recovered on attempt 2, 3 minutes after the first");
    });

    it("names back links for an attempts list", async () => {
      mockFetch(handlerFor(MAYA, UNRESOLVED).handler);
      page = await renderPage(
        <PaymentDetailPage />,
        "/payments/pay_anchor00000001?tab=attempts&period=last_7_days&outcome=failed&failure_code=issuer_unavailable&ph_period=last_7_days",
        "/payments/:paymentId",
      );
      await flush();
      expect(Array.from(page.container.querySelectorAll(".breadcrumb a")).map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
        ["Back to failed attempts", "/payments?tab=attempts&period=last_7_days&outcome=failed&failure_code=issuer_unavailable&ph_period=last_7_days"],
        ["Back to Payment Health", "/payment-health?period=last_7_days"],
      ]);
    });
  });
});

describe("attemptChainSummary", () => {
  const base = ANCHOR_DETAIL.attempts[0]!;
  const at = (n: number, outcome: AttemptItem["outcome"], created: string, completed: string | null, message: string | null = null): AttemptItem => ({
    ...base,
    id: `att_x${n}`,
    attempt_number: n,
    outcome,
    outcome_label: outcome,
    created_at: created,
    completed_at: completed,
    failure_message: message,
    failure_code: message ? "x" : null,
  });

  it("says what was recorded, in recorded-signal wording", () => {
    expect(attemptChainSummary([at(1, "succeeded", "2026-10-01T15:00:00Z", "2026-10-01T15:00:02Z")])).toBe("Succeeded on the first attempt");
    expect(
      attemptChainSummary([
        at(1, "failed", "2026-10-01T15:00:00Z", "2026-10-01T15:00:02Z", "Issuer unavailable"),
        at(2, "failed", "2026-10-01T15:05:00Z", "2026-10-01T15:05:02Z", "Issuer unavailable"),
        at(3, "succeeded", "2026-10-01T15:11:00Z", "2026-10-01T15:12:30Z"),
      ]),
    ).toBe("2 failed attempts · recovered on attempt 3, 12 minutes after the first");
    expect(attemptChainSummary([at(1, "failed", "2026-10-01T15:00:00Z", "2026-10-01T15:00:02Z", "Do not honor")])).toBe("1 failed attempt · no retry recorded · recorded signal: Do not honor");
    expect(
      attemptChainSummary([
        at(1, "failed", "2026-10-01T15:00:00Z", "2026-10-01T15:00:02Z", "Do not honor"),
        at(2, "failed", "2026-10-01T16:00:00Z", "2026-10-01T16:00:02Z", "Expired card"),
        at(3, "pending", "2026-10-01T17:00:00Z", null),
      ]),
    ).toBe("2 failed attempts · attempt 3 pending · recorded signals: Do not honor, Expired card");
    expect(
      attemptChainSummary([at(1, "failed", "2026-10-01T15:00:00Z", "2026-10-01T15:00:02Z", "Do not honor"), at(2, "succeeded", "2026-10-02T17:30:00Z", "2026-10-02T17:30:05Z")]),
    ).toBe("1 failed attempt · recovered on attempt 2, 1 day 2 hours after the first");
  });
});
