// The only place money and timestamps are formatted, and the only file that may read the browser clock.

export const REPORTING_TIMEZONE = "America/Chicago";

const MINUS = "−";

/** Integer cents to "$1,234.56" / "−$48.00". Never floats. */
export function formatCents(cents: number, options: { sign?: boolean; symbol?: boolean } = {}): string {
  const { sign = true, symbol = true } = options;
  const negative = cents < 0;
  const abs = Math.abs(Math.trunc(cents));
  const dollars = Math.floor(abs / 100);
  const rem = abs % 100;
  const dollarText = dollars.toLocaleString("en-US");
  const body = `${symbol ? "$" : ""}${dollarText}.${rem < 10 ? "0" : ""}${rem}`;
  if (negative && sign) return `${MINUS}${body}`;
  return body;
}

/** Parse a dollars string typed by a person into integer cents, or null when invalid. */
export function parseDollarsToCents(text: string): number | null {
  const raw = text.trim().replace(/[$,\s]/g, "");
  if (raw === "") return null;
  const match = /^(-)?(\d*)(?:\.(\d{0,2}))?$/.exec(raw);
  if (!match) return null;
  const [, neg, whole, frac = ""] = match;
  if (whole === "" && frac === "") return null;
  const cents = Number(whole || "0") * 100 + Number((frac + "00").slice(0, 2));
  return neg ? -cents : cents;
}

const dateTimeShort = new Intl.DateTimeFormat("en-US", {
  timeZone: REPORTING_TIMEZONE,
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});
const dateTimeShortWithYear = new Intl.DateTimeFormat("en-US", {
  timeZone: REPORTING_TIMEZONE,
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});
const dateTimeFull = new Intl.DateTimeFormat("en-US", {
  timeZone: REPORTING_TIMEZONE,
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
  timeZoneName: "short",
});
const dateOnly = new Intl.DateTimeFormat("en-US", {
  timeZone: REPORTING_TIMEZONE,
  month: "short",
  day: "numeric",
  year: "numeric",
});
const dateOnlyNoYear = new Intl.DateTimeFormat("en-US", {
  timeZone: REPORTING_TIMEZONE,
  month: "short",
  day: "numeric",
});
const weekdayDate = new Intl.DateTimeFormat("en-US", {
  timeZone: REPORTING_TIMEZONE,
  weekday: "short",
  month: "short",
  day: "numeric",
});
const timeOnly = new Intl.DateTimeFormat("en-US", {
  timeZone: REPORTING_TIMEZONE,
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});
const timeFull = new Intl.DateTimeFormat("en-US", {
  timeZone: REPORTING_TIMEZONE,
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
  timeZoneName: "short",
});
const yearOf = new Intl.DateTimeFormat("en-US", { timeZone: REPORTING_TIMEZONE, year: "numeric" });

/** Compact table timestamp: "Sep 22, 2:14 PM"; the year is added when it differs from the reporting clock's year. */
export function formatTimestamp(iso: string, asOf?: string): string {
  const d = new Date(iso);
  if (asOf && yearOf.format(d) !== yearOf.format(new Date(asOf))) {
    return dateTimeShortWithYear.format(d);
  }
  return dateTimeShort.format(d);
}

/** Full timestamp for detail pages and tooltips: "Sep 22, 2026, 2:14:03 PM CDT". */
export function formatTimestampFull(iso: string): string {
  return dateTimeFull.format(new Date(iso));
}

export function formatTime(iso: string): string {
  return timeOnly.format(new Date(iso));
}

/** Time of day with seconds, for a detail row whose date is already on screen: "2:14:53 PM CDT". */
export function formatTimeFull(iso: string): string {
  return timeFull.format(new Date(iso));
}

/** A Chicago calendar date given as YYYY-MM-DD or an instant, as "Oct 6, 2026". */
export function formatDate(value: string): string {
  return dateOnly.format(toInstant(value));
}

export function formatDateShort(value: string): string {
  return dateOnlyNoYear.format(toInstant(value));
}

export function formatWeekdayDate(value: string): string {
  return weekdayDate.format(toInstant(value));
}

function toInstant(value: string): Date {
  // A bare calendar date is a Chicago date; anchor it at noon Chicago (17:00Z or 18:00Z) so the day never shifts.
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return new Date(`${value}T12:00:00-05:00`);
  }
  return new Date(value);
}

/** Relative time against the reporting clock, never the browser clock: "12 min ago", "3 hours ago", "2 days ago". */
export function formatRelative(iso: string, asOf: string): string {
  const diffMs = new Date(asOf).getTime() - new Date(iso).getTime();
  const future = diffMs < 0;
  const abs = Math.abs(diffMs);
  const minutes = Math.round(abs / 60000);
  const hours = Math.round(abs / 3600000);
  const days = Math.round(abs / 86400000);
  let text: string;
  if (minutes < 1) text = "just now";
  else if (minutes < 60) text = `${minutes} min`;
  else if (hours < 48) text = `${hours} hour${hours === 1 ? "" : "s"}`;
  else text = `${days} day${days === 1 ? "" : "s"}`;
  if (text === "just now") return text;
  return future ? `in ${text}` : `${text} ago`;
}

/** Whole days from the reporting clock's Chicago date to a date or instant; negative when past. */
export function daysUntil(value: string, asOf: string): number {
  const target = chicagoDayNumber(toInstant(value));
  const today = chicagoDayNumber(new Date(asOf));
  return target - today;
}

const chicagoYmd = new Intl.DateTimeFormat("en-CA", { timeZone: REPORTING_TIMEZONE, year: "numeric", month: "2-digit", day: "2-digit" });

/** Chicago calendar date of an instant as YYYY-MM-DD. */
export function chicagoDate(iso: string): string {
  return chicagoYmd.format(new Date(iso));
}

function chicagoDayNumber(d: Date): number {
  const ymd = chicagoYmd.format(d); // YYYY-MM-DD
  const [y, m, day] = ymd.split("-").map(Number);
  return Math.round(Date.UTC(y, m - 1, day) / 86400000);
}

/** Greeting from the reporting clock's Chicago hour. */
export function greetingFor(asOf: string): string {
  const hour = Number(new Intl.DateTimeFormat("en-US", { timeZone: REPORTING_TIMEZONE, hour: "numeric", hourCycle: "h23" }).format(new Date(asOf)));
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export function formatCount(n: number): string {
  return n.toLocaleString("en-US");
}

/** Browser-clock read, isolated here on purpose (used only for a debounce timer id or similar, never for business dates). */
export function nowMs(): number {
  return Date.now();
}

/** Up to two initials from a person's full name, for avatars. */
export function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return `${first}${last}`.toUpperCase();
}
