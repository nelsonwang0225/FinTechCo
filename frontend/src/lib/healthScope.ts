import { queryString } from "../api/client";
import type { PeriodInfo } from "../api/payments-types";
import type { QueryState } from "./query";

/**
 * The scope of a Payment Health view (period and channel) and the links between Payment Health and the existing
 * Payments / Attempts records.
 *
 * A drill-down link carries the filters the target page reads (period, from, to, channel, status, outcome,
 * failure_code) plus the original Payment Health scope under the `ph_` prefix (`ph_period`, `ph_from`, `ph_to`,
 * `ph_channel`). The target page keeps unrelated query keys when its own filters change, so "Back to Payment
 * Health" restores the scope the person started from even after they narrowed the list further. Merchant scope is
 * never in a URL: it is the session's.
 */
export interface HealthScope {
  period: string; // a preset name, or "custom" with from and to
  from: string | null;
  to: string | null;
  channel: string | null;
}

export const HEALTH_SCOPE_PREFIX = "ph_";

/** The scope the API resolved, in the form the Payments page reads it. */
export function scopeFromPeriod(period: PeriodInfo, channel: string | null): HealthScope {
  if (period.preset === "custom") return { period: "custom", from: period.from_date, to: period.to_date, channel };
  return { period: period.preset, from: null, to: null, channel };
}

/** Query keys a list page reads for the same scope: period, from, to and channel. */
export function scopeParams(scope: HealthScope): Record<string, string | null> {
  return { period: scope.period, from: scope.from, to: scope.to, channel: scope.channel };
}

/** The same keys under the `ph_` prefix, so a target page can link back to the original scope. */
export function scopeBackParams(scope: HealthScope): Record<string, string | null> {
  const out: Record<string, string | null> = {};
  for (const [key, value] of Object.entries(scopeParams(scope))) out[`${HEALTH_SCOPE_PREFIX}${key}`] = value;
  return out;
}

export function paymentHealthHref(scope: HealthScope): string {
  return `/payment-health${queryString(scopeParams(scope))}`;
}

/**
 * The existing Payments list filtered to failed payments: exactly the unresolved payments of `scope`. `backScope` is
 * the Payment Health view the person left, when the list is narrower than it (the attention button on the
 * all-channels view opens the degraded channel's payments, and Back must still return to all channels).
 */
export function unresolvedPaymentsHref(scope: HealthScope, backScope: HealthScope = scope): string {
  return `/payments${queryString({ ...scopeParams(scope), status: "failed", ...scopeBackParams(backScope) })}`;
}

/** The existing Attempts tab filtered to failed attempts with one recorded failure code, in the same scope. */
export function failedAttemptsHref(scope: HealthScope, failureCode: string): string {
  return `/payments${queryString({ tab: "attempts", ...scopeParams(scope), outcome: "failed", failure_code: failureCode, ...scopeBackParams(scope) })}`;
}

/** The Payment Health link a list page shows when it was opened from Payment Health; null otherwise. */
export function backToHealthHref(query: QueryState): string | null {
  const period = query.get(`${HEALTH_SCOPE_PREFIX}period`);
  if (!period) return null;
  return paymentHealthHref({
    period,
    from: query.get(`${HEALTH_SCOPE_PREFIX}from`) || null,
    to: query.get(`${HEALTH_SCOPE_PREFIX}to`) || null,
    channel: query.get(`${HEALTH_SCOPE_PREFIX}channel`) || null,
  });
}
