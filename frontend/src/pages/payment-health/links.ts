import { queryString, type QueryValue } from "../../api/client";
import type { QueryState } from "../../lib/query";
import { periodParams } from "../payments/PeriodFilter";

/** The URL keys that make up a Payment Health scope; nothing else is carried back. */
const SCOPE_KEYS = ["period", "from", "to", "channel"] as const;
const SAFE_VALUE = /^[A-Za-z0-9_-]{1,40}$/;

export type HealthScope = Partial<Record<(typeof SCOPE_KEYS)[number], string>>;

/** The page's current scope: the resolved period parameters plus the channel, if one is selected. */
export function healthScope(query: QueryState): HealthScope {
  const scope: HealthScope = {};
  const params: Record<string, string | undefined> = { ...periodParams(query), channel: query.get("channel") || undefined };
  for (const key of SCOPE_KEYS) {
    const value = params[key];
    if (value) scope[key] = value;
  }
  return scope;
}

function withScope(scope: HealthScope, extra: Record<string, QueryValue>): Record<string, QueryValue> {
  // The scope travels as one `health` parameter so the destination page can offer the way back.
  return { ...scope, ...extra, health: queryString(scope).slice(1) || "period=last_7_days" };
}

/** The Payments list filtered to the scope's period and channel plus `extra` (e.g. recovery=unresolved). */
export function paymentsDrill(scope: HealthScope, extra: Record<string, QueryValue>): string {
  return `/payments${queryString(withScope(scope, extra))}`;
}

/** The Attempts tab filtered to the scope's period and channel plus `extra` (e.g. outcome and failure_code). */
export function attemptsDrill(scope: HealthScope, extra: Record<string, QueryValue>): string {
  return `/payments${queryString(withScope(scope, { tab: "attempts", ...extra }))}`;
}

/**
 * The Payment Health path for a `health` parameter found on another page. Only the scope keys with simple values are
 * kept and the path is always /payment-health, so the parameter can never point anywhere else.
 */
export function backToHealthPath(raw: string): string {
  const parsed = new URLSearchParams(raw);
  const scope: Record<string, string> = {};
  for (const key of SCOPE_KEYS) {
    const value = parsed.get(key);
    if (value && SAFE_VALUE.test(value)) scope[key] = value;
  }
  return `/payment-health${queryString(scope)}`;
}
