import { describe, expect, it } from "vitest";
import { chicagoDate, daysUntil, formatCents, formatPoints, formatRate, formatRelative, formatTimeFull, formatTimestamp, formatTimestampFull, greetingFor, parseDollarsToCents } from "./format";

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

describe("timestamps are rendered in America/Chicago", () => {
  it("formats a UTC instant as Chicago local time", () => {
    expect(formatTimestamp("2026-09-22T19:14:00Z")).toBe("Sep 22, 2:14 PM");
    expect(formatTimestamp("2025-09-22T19:14:00Z", "2026-10-05T14:12:00Z")).toBe("Sep 22, 2025, 2:14 PM");
  });
  it("renders full timestamps and same-day times with seconds and the zone", () => {
    expect(formatTimestampFull("2026-09-22T19:14:53Z")).toBe("Sep 22, 2026, 2:14:53 PM CDT");
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

describe("rates", () => {
  it("formats basis points as one-decimal percentages and signed points without floats", () => {
    expect(formatRate(7204)).toBe("72.0%");
    expect(formatRate(9079)).toBe("90.8%");
    expect(formatRate(10000)).toBe("100.0%");
    expect(formatRate(0)).toBe("0.0%");
    expect(formatRate(null)).toBe("—");
    expect(formatPoints(-1875)).toBe("−18.8 pts");
    expect(formatPoints(107)).toBe("+1.1 pts");
    expect(formatPoints(-4)).toBe("0.0 pts");
    expect(formatPoints(null)).toBe("—");
    expect(formatPoints(1000, { signed: false })).toBe("10.0 pts");
  });
});
