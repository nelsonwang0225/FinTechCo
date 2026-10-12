// Drill-down links from Payment Health into the existing Payments and Attempts lists, carrying the same period and
// channel plus a `return_to` that restores the Payment Health scope.

const HEALTH_PATH = "/payment-health";

export type Scope = Record<string, string | undefined>;

function withParams(path: string, params: Scope): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value);
  }
  const text = search.toString();
  return text ? `${path}?${text}` : path;
}

/** The Payment Health URL for a scope (period params plus optional channel). */
export function healthPath(scope: Scope): string {
  return withParams(HEALTH_PATH, scope);
}

/** Attempts tab filtered to the scope, e.g. `{ outcome: "failed", failure_code: "issuer_unavailable" }`. */
export function attemptsLink(scope: Scope, filters: Scope, returnTo: string): string {
  return withParams("/payments", { tab: "attempts", ...scope, ...filters, return_to: returnTo });
}

/** Payments tab filtered to the scope, e.g. `{ status: "failed" }` for unresolved payments. */
export function paymentsLink(scope: Scope, filters: Scope, returnTo: string): string {
  return withParams("/payments", { ...scope, ...filters, return_to: returnTo });
}

/** Only a Payment Health path is honoured as a return target, so the parameter cannot send anyone elsewhere. */
export function safeHealthReturn(value: string): string | null {
  if (value === HEALTH_PATH || value.startsWith(`${HEALTH_PATH}?`)) return value;
  return null;
}
