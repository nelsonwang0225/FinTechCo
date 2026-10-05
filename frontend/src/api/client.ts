// The one fetch wrapper. Cookies always travel; 401 tells the session provider to drop to the persona chooser;
// 403 and 404 surface as ApiError so pages render their forbidden and not-found states.

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

type UnauthenticatedListener = () => void;
const unauthenticatedListeners = new Set<UnauthenticatedListener>();

export function onUnauthenticated(listener: UnauthenticatedListener): () => void {
  unauthenticatedListeners.add(listener);
  return () => {
    unauthenticatedListeners.delete(listener);
  };
}

export interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  json?: unknown;
  signal?: AbortSignal;
}

function parseError(status: number, data: unknown): ApiError {
  const body = data as Partial<{ error: { code?: string; message?: string } }> | null;
  const code = body?.error?.code ?? defaultCode(status);
  const message = body?.error?.message ?? defaultMessage(status);
  return new ApiError(status, code, message);
}

function defaultCode(status: number): string {
  if (status === 401) return "unauthenticated";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  return "error";
}

function defaultMessage(status: number): string {
  if (status === 401) return "Sign in to continue.";
  if (status === 403) return "Your role does not include this.";
  if (status === 404) return "Not found in this business.";
  return `Request failed (${status}).`;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers({ Accept: "application/json" });
  let body: string | undefined;
  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.json);
  }
  let response: Response;
  try {
    response = await fetch(path, { method: options.method ?? "GET", headers, body, credentials: "include", signal: options.signal });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, "network", "Could not reach the server.");
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    const error = parseError(response.status, data);
    if (response.status === 401 && !path.startsWith("/api/dev/")) {
      for (const listener of unauthenticatedListeners) listener();
    }
    throw error;
  }
  return data as T;
}

export type QueryValue = string | number | boolean | null | undefined;

/** Build a query string, dropping empty values. Keys are emitted in the given order. */
export function queryString(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
