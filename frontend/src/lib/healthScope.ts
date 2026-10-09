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

/**
 * The existing Attempts tab filtered to failed attempts in `scope`, optionally narrowed to one recorded failure code.
 * `backScope` works as for unresolvedPaymentsHref: a channel row on the all-channels view returns to all channels.
 */
export function failedAttemptsHref(scope: HealthScope, failureCode: string | null = null, backScope: HealthScope = scope): string {
  return `/payments${queryString({ tab: "attempts", ...scopeParams(scope), outcome: "failed", failure_code: failureCode, ...scopeBackParams(backScope) })}`;
}

/** A payment detail link from Payment Health's own unresolved table: it carries the unresolved list it belongs to. */
export function unresolvedPaymentDetailHref(paymentId: string, scope: HealthScope): string {
  return `/payments/${encodeURIComponent(paymentId)}${queryString({ ...scopeParams(scope), status: "failed", ...scopeBackParams(scope) })}`;
}

/** True when the current list or detail page was reached from Payment Health. */
export function fromHealth(query: QueryState): boolean {
  return query.get(`${HEALTH_SCOPE_PREFIX}period`) !== "";
}

/**
 * A payment detail link from a list. Reached from Payment Health, it carries the whole list query (filters, tab, sort,
 * page and the `ph_` scope) so the detail page can link back to exactly that list and on to Payment Health.
 */
export function paymentDetailHref(paymentId: string, query: QueryState): string {
  const path = `/payments/${encodeURIComponent(paymentId)}`;
  return fromHealth(query) && query.search ? `${path}?${query.search}` : path;
}

/** The list a detail page was opened from, when that list was reached from Payment Health; null otherwise. */
export function backToListLink(query: QueryState): { href: string; label: string } | null {
  if (!fromHealth(query)) return null;
  const href = `/payments?${query.search}`;
  if (query.get("tab") === "attempts") return { href, label: query.get("outcome") === "failed" ? "Back to failed attempts" : "Back to attempts" };
  return { href, label: query.get("status") === "failed" ? "Back to unresolved payments" : "Back to payments" };
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
