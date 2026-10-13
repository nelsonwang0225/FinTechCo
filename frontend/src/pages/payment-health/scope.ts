import { queryString, type QueryValue } from "../../api/client";
import type { QueryState } from "../../lib/query";
import { periodParams } from "../payments/PeriodFilter";

/** URL key that carries the Payment Health scope into the Payments and Attempts lists, for the way back. */
export const HEALTH_SCOPE_PARAM = "ph";

const PRESETS = new Set(["last_7_days", "last_30_days", "month_to_date", "custom"]);
const CHANNELS = new Set(["website", "mobile_app", "in_store"]);
const DATE = /^\d{4}-\d{2}-\d{2}$/;

/** The Payment Health scope being shown (period as resolved for the API, plus channel), encoded for the `ph` parameter. */
export function encodeHealthScope(query: QueryState): string {
  return queryString({ ...periodParams(query), channel: query.get("channel") }).replace(/^\?/, "");
}

/**
 * The link back to Payment Health from a `ph` value, or null when there is none. Only the four scope keys are kept and
 * each is checked, so the value can never send the browser anywhere but /payment-health.
 */
export function backToHealthHref(ph: string): string | null {
  if (!ph) return null;
  const raw = new URLSearchParams(ph);
  const kept: Record<string, QueryValue> = {};
  const period = raw.get("period");
  if (period && PRESETS.has(period)) kept.period = period;
  for (const key of ["from", "to"]) {
    const value = raw.get(key);
    if (value && DATE.test(value)) kept[key] = value;
  }
  const channel = raw.get("channel");
  if (channel && CHANNELS.has(channel)) kept.channel = channel;
  return `/payment-health${queryString(kept)}`;
}

/** A Payments or Attempts list URL for the same period (and channel unless overridden) that knows its way back. */
export function drillHref(query: QueryState, extra: Record<string, QueryValue>, channel: string | null = query.get("channel") || null): string {
  const { tab, ...rest } = extra;
  return `/payments${queryString({ tab, ...periodParams(query), channel, ...rest, [HEALTH_SCOPE_PARAM]: encodeHealthScope(query) })}`;
}
