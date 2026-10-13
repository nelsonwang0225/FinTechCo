import { queryString } from "../../api/client";
import type { QueryState } from "../../lib/query";
import { periodParams } from "../payments/PeriodFilter";

/** The URL keys that make up a Payment Health scope; also the only keys a back link may carry. */
const SCOPE_KEYS = ["period", "from", "to", "channel"] as const;

export interface HealthScope {
  period?: string;
  from?: string;
  to?: string;
  channel?: string;
}

/** The scope the page is showing, resolved the same way the API call is, so drill-downs count the same rows. */
export function healthScope(query: QueryState): HealthScope {
  return { ...periodParams(query), channel: query.get("channel") || undefined };
}

function scopeParams(scope: HealthScope): Record<string, string | undefined> {
  return { period: scope.period, from: scope.from, to: scope.to, channel: scope.channel };
}

/** The scope as a bare query string, carried in `back` so the Payments views can link back to it. */
function scopeSearch(scope: HealthScope): string {
  return queryString(scopeParams(scope)).replace(/^\?/, "");
}

/** Failed attempts carrying one recorded failure signal, on the Attempts tab. */
export function attemptsHref(scope: HealthScope, failureCode: string): string {
  return `/payments${queryString({ tab: "attempts", ...scopeParams(scope), outcome: "failed", failure_code: failureCode, back: scopeSearch(scope) })}`;
}

/** Unresolved payments (status failed) created in the scope, on the Payments tab; `channel` narrows an all-channel scope. */
export function unresolvedHref(scope: HealthScope, channel?: string): string {
  const narrowed = channel ? { ...scope, channel } : scope;
  return `/payments${queryString({ ...scopeParams(narrowed), status: "failed", back: scopeSearch(scope) })}`;
}

/**
 * Rebuild "Back to Payment Health" from a `back` parameter. Only the scope keys survive, and the path is fixed, so a
 * crafted link cannot send anyone elsewhere.
 */
export function backToHealthHref(back: string): string | null {
  if (!back) return null;
  const parsed = new URLSearchParams(back);
  const kept: Record<string, string | undefined> = {};
  for (const key of SCOPE_KEYS) kept[key] = parsed.get(key) ?? undefined;
  return `/payment-health${queryString(kept)}`;
}
