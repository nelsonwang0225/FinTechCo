import { queryString, type QueryValue } from "../../api/client";
import type { QueryState } from "../../lib/query";
import { periodParams } from "../payments/PeriodFilter";

export type HealthScope = Record<string, QueryValue>;

/** The page's scope as it appears in the URL: the period and, optionally, one channel. */
export function healthScope(query: QueryState): HealthScope {
  return { ...periodParams(query), channel: query.get("channel") || undefined };
}

export function healthHref(scope: HealthScope): string {
  return `/payment-health${queryString(scope)}`;
}

/** Failed attempts in the same period and channel, optionally for one recorded signal, on the Attempts tab. */
export function failedAttemptsHref(scope: HealthScope, options: { channel?: string | null; failureCode?: string } = {}): string {
  const channel = options.channel === undefined ? scope.channel : options.channel;
  return `/payments${queryString({ tab: "attempts", ...scope, channel, outcome: "failed", failure_code: options.failureCode, back: healthHref(scope) })}`;
}

/** Unresolved payments (no success, latest attempt failed) created in the same period and channel, on the Payments tab. */
export function unresolvedPaymentsHref(scope: HealthScope, options: { channel?: string | null } = {}): string {
  const channel = options.channel === undefined ? scope.channel : options.channel;
  return `/payments${queryString({ ...scope, channel, status: "failed", back: healthHref(scope) })}`;
}

/** Only a Payment Health path is accepted as a return link, so the parameter can never send someone elsewhere. */
export function safeHealthBack(value: string): string | null {
  return value === "/payment-health" || value.startsWith("/payment-health?") ? value : null;
}
