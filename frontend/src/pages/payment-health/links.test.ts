import { describe, expect, it } from "vitest";
import { attemptsHref, backToHealthHref, unresolvedHref } from "./links";

describe("Payment Health drill-down links", () => {
  const scope = { period: "custom", from: "2026-10-01", to: "2026-10-02", channel: "mobile_app" };

  it("opens failed attempts for one signal with the same period and channel", () => {
    const href = new URL(attemptsHref(scope, "issuer_unavailable"), "http://x");
    expect(href.pathname).toBe("/payments");
    expect(Object.fromEntries(href.searchParams)).toEqual({
      tab: "attempts",
      period: "custom",
      from: "2026-10-01",
      to: "2026-10-02",
      channel: "mobile_app",
      outcome: "failed",
      failure_code: "issuer_unavailable",
      back: "period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app",
    });
  });

  it("opens unresolved payments, optionally narrowed to one channel while the back link keeps the original scope", () => {
    const href = new URL(unresolvedHref({ period: "last_7_days" }, "website"), "http://x");
    expect(href.searchParams.get("channel")).toBe("website");
    expect(href.searchParams.get("status")).toBe("failed");
    expect(href.searchParams.get("back")).toBe("period=last_7_days");
  });

  it("rebuilds the back link from scope keys only, on a fixed path", () => {
    expect(backToHealthHref("period=last_7_days&channel=mobile_app")).toBe("/payment-health?period=last_7_days&channel=mobile_app");
    expect(backToHealthHref("period=custom&from=2026-10-01&to=2026-10-02&next=https://evil.example.com")).toBe("/payment-health?period=custom&from=2026-10-01&to=2026-10-02");
    expect(backToHealthHref("//evil.example.com")).toBe("/payment-health");
    expect(backToHealthHref("")).toBeNull();
  });
});
