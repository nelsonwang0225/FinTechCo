import { queryString } from "../../api/client";
import type { QueryState } from "../../lib/query";
import { periodParams } from "../payments/PeriodFilter";

/** The URL keys that make up a Payment Health scope. A drill-down carries them in `health` so the way back restores them. */
const SCOPE_KEYS = ["period", "from", "to", "channel"] as const;

/** Period and channel as the API and the drill-down lists take them. */
export function healthScope(query: QueryState): Record<string, string | undefined> {
  return { ...periodParams(query), channel: query.get("channel") || undefined };
}

/** The value of the `health` parameter that drill-down links carry: the page's effective scope, never empty. */
export function healthReturnValue(query: QueryState): string {
  return queryString(healthScope(query)).slice(1);
}

/** "/payment-health?…" rebuilt from a `health` value, keeping only the scope keys so nothing else rides along. */
export function healthBackHref(raw: string): string {
  const source = new URLSearchParams(raw);
  const out = new URLSearchParams();
  for (const key of SCOPE_KEYS) {
    const value = source.get(key);
    if (value) out.set(key, value);
  }
  const text = out.toString();
  return `/payment-health${text ? `?${text}` : ""}`;
}

/**
 * A link into the Payments page (or its Attempts tab) with the health scope applied and a way back. A filter may name a
 * narrower channel than the page scope (an attention item names its own).
 */
export function drillHref(query: QueryState, filters: Record<string, string | undefined>): string {
  const scope = healthScope(query);
  return `/payments${queryString({ ...filters, ...scope, channel: filters.channel ?? scope.channel, health: healthReturnValue(query) })}`;
}
