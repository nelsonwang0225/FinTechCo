import { describe, expect, it } from "vitest";
import { backToHealthHref } from "./scope";

describe("backToHealthHref", () => {
  it("rebuilds the Payment Health scope from the ph parameter", () => {
    expect(backToHealthHref("period=last_7_days")).toBe("/payment-health?period=last_7_days");
    expect(backToHealthHref("period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app")).toBe(
      "/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app",
    );
  });

  it("is absent without a scope", () => {
    expect(backToHealthHref("")).toBeNull();
  });

  it("keeps only known keys and valid values, so it can only lead to /payment-health", () => {
    expect(backToHealthHref("period=last_30_days&next=https://example.com&channel=atm&from=tomorrow")).toBe("/payment-health?period=last_30_days");
    expect(backToHealthHref("//example.com/evil")).toBe("/payment-health");
  });
});
