import { queryString, type QueryValue } from "../../api/client";
import type { QueryState } from "../../lib/query";

/** The Payment Health scope a drill-down came from: the API's period params plus the channel (empty for all). */
export interface HealthScope {
  period: Record<string, string | undefined>;
  channel: string;
}

// Drill-downs carry the original Health scope under this prefix (the lib/scopedQuery convention). The Payments page's
// own filters, tab switches and "Clear all" never touch these keys, so "Back to Payment Health" restores the scope the
// person started from, not whatever they filtered to afterwards.
const PREFIX = "health";
const SCOPE_KEYS = ["period", "from", "to", "channel"] as const;

function carried(scope: HealthScope): Record<string, QueryValue> {
  const values: Record<string, string | undefined> = { ...scope.period, channel: scope.channel || undefined };
  return Object.fromEntries(SCOPE_KEYS.map((k) => [`${PREFIX}_${k}`, values[k]]));
}

/** The Payments list (or its Attempts tab) narrowed to the scope plus `extra`, remembering where it came from. */
export function drillDownHref(scope: HealthScope, extra: Record<string, QueryValue>, channel: string = scope.channel): string {
  return `/payments${queryString({ ...extra, ...scope.period, channel: channel || undefined, ...carried(scope) })}`;
}

export function attemptsHref(scope: HealthScope, extra: Record<string, QueryValue> = {}, channel?: string): string {
  return drillDownHref(scope, { tab: "attempts", ...extra }, channel);
}

export function unresolvedPaymentsHref(scope: HealthScope, channel?: string): string {
  return drillDownHref(scope, { status: "failed" }, channel);
}

/** "/payment-health?…" rebuilt from the carried keys, or null when the page was not opened from Payment Health. */
export function backToHealthHref(query: QueryState): string | null {
  if (!query.get(`${PREFIX}_period`)) return null;
  return `/payment-health${queryString(Object.fromEntries(SCOPE_KEYS.map((k) => [k, query.get(`${PREFIX}_${k}`) || undefined])))}`;
}
