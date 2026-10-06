import { afterEach, describe, expect, it } from "vitest";
import type { PaymentHealth } from "../../api/payment-health-types";
import { formatRateBp } from "../../lib/format";
import { META } from "../../test/fixtures";
import { MAYA, mockFetch, type Handler } from "../../test/mockApi";
import { flush, renderPage, type Rendered } from "../../test/render";
import { PaymentHealthPage } from "./PaymentHealthPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

/** The seeded Oct 1–2 mobile-app incident at Alder & Loom, as the API returns it. */
const INCIDENT: PaymentHealth = {
  period: { preset: "custom", label: "Custom range", from_date: "2026-10-01", to_date: "2026-10-02", range_label: "Oct 1 – Oct 2, 2026" },
  channel: "mobile_app",
  channel_label: "Mobile app",
  as_of: "2026-10-05T14:12:00Z",
  attempts: { succeeded: 53, failed: 42, completed: 95, pending_excluded: 0, success_rate_bp: 5579, low_volume: false, low_volume_threshold: 30 },
  trend: {
    granularity: "day",
    points: [
      { day: "2026-10-01", succeeded: 25, failed: 31 },
      { day: "2026-10-02", succeeded: 28, failed: 11 },
    ],
  },
  failure_signals: {
    total_failed: 42,
    items: [
      { failure_code: "issuer_unavailable", label: "Issuer unavailable", count: 29 },
      { failure_code: "do_not_honor", label: "Do not honor", count: 3 },
      { failure_code: "insufficient_funds", label: "Insufficient funds", count: 3 },
      { failure_code: "processing_error", label: "Processing error", count: 3 },
      { failure_code: "authentication_failed", label: "Authentication failed", count: 1 },
      { failure_code: "card_velocity_exceeded", label: "Card velocity exceeded", count: 1 },
      { failure_code: "expired_card", label: "Expired card", count: 1 },
      { failure_code: "incorrect_cvc", label: "Incorrect security code", count: 1 },
    ],
  },
  recovery: {
    affected_payments: 38,
    recovered: 26,
    recovered_within_hour: 26,
    unresolved: 12,
    attempt_pending: 0,
    affected_cents: 896010,
    recovered_cents: 473199,
    unresolved_cents: 422811,
    attempt_pending_cents: 0,
    currency: "USD",
  },
};

const NOTHING_COMPLETED: PaymentHealth = {
  ...INCIDENT,
  channel: "website",
  channel_label: "Website",
  attempts: { succeeded: 0, failed: 0, completed: 0, pending_excluded: 2, success_rate_bp: null, low_volume: true, low_volume_threshold: 30 },
  trend: { granularity: "day", points: [{ day: "2026-10-05", succeeded: 0, failed: 0 }] },
  failure_signals: { total_failed: 0, items: [] },
  recovery: { ...INCIDENT.recovery, affected_payments: 0, recovered: 0, recovered_within_hour: 0, unresolved: 0, affected_cents: 0, recovered_cents: 0, unresolved_cents: 0 },
};

function handlerFor(body: PaymentHealth): Handler {
  return (url) => {
    if (url === "/api/session") return { status: 200, body: MAYA };
    if (url === "/api/meta") return { status: 200, body: META };
    if (url.startsWith("/api/payment-health")) return { status: 200, body };
    return undefined;
  };
}

describe("PaymentHealthPage", () => {
  it("asks for the last 7 days by default", async () => {
    const { calls } = mockFetch(handlerFor(INCIDENT));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(calls.find((c) => c.url.startsWith("/api/payment-health"))?.url).toBe("/api/payment-health?period=last_7_days");
  });

  it("shows the completed-attempt rate, recovery counted per payment, and recorded signals", async () => {
    const { calls } = mockFetch(handlerFor(INCIDENT));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app");
    await flush();
    const text = page.container.textContent ?? "";
    expect(calls.find((c) => c.url.startsWith("/api/payment-health"))?.url).toBe(
      "/api/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app",
    );
    expect(text).toContain("Attempt success rate55.8%53 succeeded of 95 completed · 0 pending excluded");
    expect(text).toContain("Affected payments3826 recovered (26 within 1 hour) · 12 unresolved");
    expect(text).toContain("$8,960.10");
    expect(text).not.toContain("Low volume");
    expect(text).toContain("Recorded failure signals");
    expect(text).toContain("not confirmed root causes");
    expect(page.container.querySelector("tbody tr")?.textContent).toContain("Issuer unavailable");
    expect(page.container.querySelector("svg[role=img] title")?.textContent).toBe("Failed attempts by day, Mobile app, Oct 1 – Oct 2, 2026");
  });

  it("drills down to failed payments in the existing Payments list with the same dates and channel", async () => {
    mockFetch(handlerFor(INCIDENT));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app");
    await flush();
    const link = Array.from(page.container.querySelectorAll("a")).find((a) => a.textContent === "Review unresolved payments");
    expect(link?.getAttribute("href")).toBe("/payments?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app&status=failed");
  });

  it("flags low volume instead of drawing a conclusion", async () => {
    const low: PaymentHealth = { ...INCIDENT, attempts: { ...INCIDENT.attempts, succeeded: 3, failed: 2, completed: 5, success_rate_bp: 6000, low_volume: true } };
    mockFetch(handlerFor(low));
    page = await renderPage(<PaymentHealthPage />, "/payment-health");
    await flush();
    expect(page.container.textContent).toContain("60.0%");
    expect(page.container.textContent).toContain("Low volume: fewer than 30 completed attempts, not enough to judge.");
  });

  it("shows an empty state and no rate when nothing completed", async () => {
    mockFetch(handlerFor(NOTHING_COMPLETED));
    page = await renderPage(<PaymentHealthPage />, "/payment-health?channel=website");
    await flush();
    const text = page.container.textContent ?? "";
    expect(text).toContain("No completed attempts in this period");
    expect(text).toContain("2 attempts are still pending");
    expect(text).not.toContain("%");
  });

  it("formats basis points half-up", () => {
    expect([formatRateBp(5579), formatRateBp(10000), formatRateBp(4464), formatRateBp(5), formatRateBp(4)]).toEqual(["55.8%", "100.0%", "44.6%", "0.1%", "0.0%"]);
  });
});
