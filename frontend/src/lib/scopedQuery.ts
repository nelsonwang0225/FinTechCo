import type { QueryPatch, QueryState } from "./query";

/**
 * A view of the URL query state under a key prefix, so several independent filter groups (one per report card)
 * can share one URL without colliding: `scoped(query, "pr").get("period")` reads `pr_period`.
 */
export function scopedQuery(query: QueryState, prefix: string): QueryState {
  const key = (k: string) => `${prefix}_${k}`;
  return {
    get: (k, fallback) => query.get(key(k), fallback),
    getInt: (k, fallback) => query.getInt(key(k), fallback),
    set: (patch: QueryPatch, options) => {
      const scoped: QueryPatch = {};
      for (const [k, v] of Object.entries(patch)) scoped[key(k)] = v;
      query.set(scoped, { keepPage: true, ...options });
    },
    search: query.search,
  };
}
