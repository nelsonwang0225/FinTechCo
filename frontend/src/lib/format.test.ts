import { describe, expect, it } from "vitest";
import { chicagoDate, daysUntil, formatCents, formatPointsBp, formatRateBp, formatRelative, formatTimeFull, formatTimestamp, formatTimestampFull, formatTimestampMinute, greetingFor, parseDollarsToCents } from "./format";

describe("formatCents", () => {
  it("formats integer cents without floating point", () => {
    expect(formatCents(123456789)).toBe("$1,234,567.89");
    expect(formatCents(5)).toBe("$0.05");
    expect(formatCents(-4850)).toBe("−$48.50");
    expect(formatCents(-4850, { sign: false })).toBe("$48.50");
    expect(formatCents(100, { symbol: false })).toBe("1.00");
  });
});

describe("parseDollarsToCents", () => {
  it("parses typed dollars into cents", () => {
    expect(parseDollarsToCents("1,234.5")).toBe(123450);
    expect(parseDollarsToCents("$12")).toBe(1200);
    expect(parseDollarsToCents("-3.07")).toBe(-307);
    expect(parseDollarsToCents("")).toBeNull();
    expect(parseDollarsToCents("1.234")).toBeNull();
    expect(parseDollarsToCents("abc")).toBeNull();
  });
});

describe("rates in basis points", () => {
  it("renders a rate with one decimal, rounded half-up, in integer arithmetic", () => {
    expect(formatRateBp(5579)).toBe("55.8%");
    expect(formatRateBp(7204)).toBe("72.0%");
    expect(formatRateBp(10000)).toBe("100.0%");
    expect(formatRateBp(4)).toBe("0.0%");
    expect(formatRateBp(5)).toBe("0.1%");
    expect(formatRateBp(0)).toBe("0.0%");
  });
  it("renders a difference as signed percentage points with a true minus sign", () => {
    expect(formatPointsBp(-1875)).toBe("−18.8 pts");
    expect(formatPointsBp(106)).toBe("+1.1 pts");
    expect(formatPointsBp(0)).toBe("0.0 pts");
    expect(formatPointsBp(-4)).toBe("0.0 pts");
    expect(formatPointsBp(3515)).toBe("+35.2 pts");
  });
});

describe("timestamps are rendered in America/Chicago", () => {
  it("formats a UTC instant as Chicago local time", () => {
    expect(formatTimestamp("2026-09-22T19:14:00Z")).toBe("Sep 22, 2:14 PM");
    expect(formatTimestamp("2025-09-22T19:14:00Z", "2026-10-05T14:12:00Z")).toBe("Sep 22, 2025, 2:14 PM");
  });
  it("renders full timestamps and same-day times with seconds and the zone", () => {
    expect(formatTimestampFull("2026-09-22T19:14:53Z")).toBe("Sep 22, 2026, 2:14:53 PM CDT");
    expect(formatTimestampMinute("2026-10-05T14:12:00Z")).toBe("Oct 5, 2026, 9:12 AM CDT");
    expect(formatTimestampMinute("2026-01-05T14:12:30Z")).toBe("Jan 5, 2026, 8:12 AM CST");
    expect(formatTimeFull("2026-09-22T19:14:53Z")).toBe("2:14:53 PM CDT");
    expect(formatTimeFull("2026-11-02T19:14:53Z")).toBe("1:14:53 PM CST");
  });
  it("buckets late evening Chicago instants on the right day", () => {
    expect(chicagoDate("2026-09-30T04:30:00Z")).toBe("2026-09-29");
  });
  it("computes relative time against the reporting clock", () => {
    expect(formatRelative("2026-10-05T14:00:00Z", "2026-10-05T14:12:00Z")).toBe("12 min ago");
    expect(formatRelative("2026-10-05T14:12:00Z", "2026-10-05T14:12:00Z")).toBe("just now");
    expect(formatRelative("2026-10-02T14:12:00Z", "2026-10-05T14:12:00Z")).toBe("3 days ago");
  });
  it("counts days until a Chicago date from the reporting clock", () => {
    expect(daysUntil("2026-10-07", "2026-10-05T14:12:00Z")).toBe(2);
    expect(daysUntil("2026-10-07T23:59:00Z", "2026-10-05T14:12:00Z")).toBe(2);
  });
  it("greets by the reporting clock's hour", () => {
    expect(greetingFor("2026-10-05T14:12:00Z")).toBe("Good morning");
    expect(greetingFor("2026-10-05T20:12:00Z")).toBe("Good afternoon");
    expect(greetingFor("2026-10-06T01:12:00Z")).toBe("Good evening");
  });
});
