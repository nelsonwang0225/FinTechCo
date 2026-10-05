import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

export type QueryPatch = Record<string, string | number | null | undefined>;

export interface QueryState {
  /** Read one parameter, with a fallback. */
  get: (key: string, fallback?: string) => string;
  /** Read an integer parameter (>= 1), with a fallback. */
  getInt: (key: string, fallback: number) => number;
  /** Merge a patch into the URL; null, undefined and "" remove the key. Resets `page` unless the patch sets it. */
  set: (patch: QueryPatch, options?: { keepPage?: boolean; replace?: boolean }) => void;
  /** The raw string, for building API paths. */
  search: string;
}

/** Filters, sort, page and tab live in the URL so a view can be shared and survives refresh. */
export function useQueryState(): QueryState {
  const [params, setParams] = useSearchParams();

  const get = useCallback((key: string, fallback = "") => params.get(key) ?? fallback, [params]);
  const getInt = useCallback(
    (key: string, fallback: number) => {
      const raw = params.get(key);
      const n = raw === null ? Number.NaN : Number.parseInt(raw, 10);
      return Number.isFinite(n) && n >= 1 ? n : fallback;
    },
    [params],
  );
  const set = useCallback(
    (patch: QueryPatch, options: { keepPage?: boolean; replace?: boolean } = {}) => {
      const next = new URLSearchParams(params);
      if (!options.keepPage && !("page" in patch)) next.delete("page");
      for (const [key, value] of Object.entries(patch)) {
        if (value === null || value === undefined || value === "") next.delete(key);
        else next.set(key, String(value));
      }
      setParams(next, { replace: options.replace ?? false });
    },
    [params, setParams],
  );

  return useMemo(() => ({ get, getInt, set, search: params.toString() }), [get, getInt, set, params]);
}
