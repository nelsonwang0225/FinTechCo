import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiFetch } from "./client";

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Fetch `path` whenever it changes. A null path means "nothing to load yet".
 * The previous data stays on screen while a new path loads so lists do not flash.
 */
export function useApi<T>(path: string | null): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(path !== null);
  const [tick, setTick] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    if (path === null) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const request = ++latest.current;
    setLoading(true);
    setError(null);
    apiFetch<T>(path, { signal: controller.signal })
      .then((result) => {
        if (request !== latest.current) return;
        setData(result);
        setLoading(false);
      })
      .catch((cause: unknown) => {
        if (request !== latest.current) return;
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setError(cause instanceof ApiError ? cause : new ApiError(0, "error", "Something went wrong."));
        setData(null);
        setLoading(false);
      });
    return () => controller.abort();
  }, [path, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, loading, reload };
}
