import { describe, expect, it } from "vitest";
import { attemptsLink, healthPath, paymentsLink, safeHealthReturn } from "./healthLinks";

describe("Payment Health drill-down links", () => {
  const scope = { period: "custom", from: "2026-09-29", to: "2026-10-05", channel: "mobile_app" };
  const back = healthPath(scope);

  it("carries the period, channel and a return path into the lists", () => {
    expect(back).toBe("/payment-health?period=custom&from=2026-09-29&to=2026-10-05&channel=mobile_app");
    const attempts = new URL(attemptsLink(scope, { outcome: "failed", failure_code: "issuer_unavailable" }, back), "http://x");
    expect(attempts.pathname).toBe("/payments");
    expect(Object.fromEntries(attempts.searchParams)).toEqual({ tab: "attempts", ...scope, outcome: "failed", failure_code: "issuer_unavailable", return_to: back });
    const payments = new URL(paymentsLink({ period: "last_7_days", channel: undefined }, { status: "failed" }, "/payment-health?period=last_7_days"), "http://x");
    expect(Object.fromEntries(payments.searchParams)).toEqual({ period: "last_7_days", status: "failed", return_to: "/payment-health?period=last_7_days" });
  });

  it("only honours a Payment Health path as the return target", () => {
    expect(safeHealthReturn(back)).toBe(back);
    expect(safeHealthReturn("/payment-health")).toBe("/payment-health");
    expect(safeHealthReturn("")).toBeNull();
    expect(safeHealthReturn("https://example.com/payment-health")).toBeNull();
    expect(safeHealthReturn("//example.com")).toBeNull();
    expect(safeHealthReturn("/payment-healthy")).toBeNull();
    expect(safeHealthReturn("/settings")).toBeNull();
  });
});
