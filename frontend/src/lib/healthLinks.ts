import { queryString } from "../api/client";

/** The Payment Health path a drill-down may return to. Anything else is ignored so `return` can never leave the app. */
export const HEALTH_PATH = "/payment-health";

export function isHealthReturn(value: string): boolean {
  return value === HEALTH_PATH || value.startsWith(`${HEALTH_PATH}?`);
}

/** Payments list: payments in the scope that are still unresolved (no success and the latest attempt failed). */
export function unresolvedPaymentsHref(scope: Record<string, string | undefined>, returnTo: string): string {
  return `/payments${queryString({ ...scope, status: "failed", return: returnTo })}`;
}

/** Attempts tab: failed attempts in the scope, optionally with one recorded failure code. */
export function failedAttemptsHref(scope: Record<string, string | undefined>, returnTo: string, failureCode?: string): string {
  return `/payments${queryString({ tab: "attempts", ...scope, outcome: "failed", failure_code: failureCode, return: returnTo })}`;
}
