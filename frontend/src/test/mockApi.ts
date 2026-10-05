import { vi } from "vitest";
import type { PersonasResponse, Session } from "../api/types";

export const ALDER = { id: "mer_alderloom00001", name: "Alder & Loom", slug: "alder-loom" };
export const JUNIPER = { id: "mer_junipertrail01", name: "Juniper Trail Outfitters", slug: "juniper-trail" };

export const MAYA: Session = {
  membership_id: "mem_maya0000000001",
  user: { id: "usr_maya0000000001", full_name: "Maya Chen", email: "maya.chen@alder-loom.example.com", title: "Operations Manager" },
  merchant: ALDER,
  role: "operations_manager",
  role_label: "Operations manager",
  permissions: ["overview:read", "payments:read", "customers:read", "disputes:read", "notes:write", "reports:operational"],
  as_of: "2026-10-05T14:12:00Z",
  timezone: "America/Chicago",
};

export const PRIYA: Session = {
  membership_id: "mem_priya000000001",
  user: { id: "usr_priya000000001", full_name: "Priya Shah", email: "priya.shah@junipertrail.example.com", title: "Operations Manager" },
  merchant: JUNIPER,
  role: "operations_manager",
  role_label: "Operations manager",
  permissions: ["overview:read", "payments:read", "customers:read", "disputes:read", "notes:write", "reports:operational"],
  as_of: "2026-10-05T14:12:00Z",
  timezone: "America/Chicago",
};

export const PERSONAS: PersonasResponse = {
  merchants: [
    {
      merchant: ALDER,
      personas: [{ membership_id: MAYA.membership_id, user_id: MAYA.user.id, full_name: "Maya Chen", title: "Operations Manager", role: "operations_manager", role_label: "Operations manager" }],
    },
    {
      merchant: JUNIPER,
      personas: [{ membership_id: PRIYA.membership_id, user_id: PRIYA.user.id, full_name: "Priya Shah", title: "Operations Manager", role: "operations_manager", role_label: "Operations manager" }],
    },
  ],
};

export type Handler = (url: string, init: RequestInit | undefined) => { status: number; body?: unknown } | undefined;

export function jsonResponse(status: number, body?: unknown): Response {
  if (status === 204) return new Response(null, { status });
  return new Response(JSON.stringify(body ?? null), { status, headers: { "Content-Type": "application/json" } });
}

/** Install a fetch mock routed through `handler`; unmatched requests answer 404. Returns the recorded calls. */
export function mockFetch(handler: Handler): { calls: { url: string; method: string; body: unknown }[] } {
  const calls: { url: string; method: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : null;
    calls.push({ url, method, body });
    const result = handler(url, init);
    if (!result) return jsonResponse(404, { error: { code: "not_found", message: "no mock for " + url } });
    return jsonResponse(result.status, result.body);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

/** A handler for the session flow: anonymous until a dev session is started, then the chosen persona. */
export function sessionFlow(sessions: Session[]): Handler {
  let current: Session | null = null;
  return (url, init) => {
    const method = init?.method ?? "GET";
    if (url === "/api/session" && method === "GET") {
      return current ? { status: 200, body: current } : { status: 401, body: { error: { code: "unauthenticated", message: "Sign in to continue." } } };
    }
    if (url === "/api/session" && method === "DELETE") {
      current = null;
      return { status: 204 };
    }
    if (url === "/api/dev/personas") return { status: 200, body: PERSONAS };
    if (url === "/api/dev/session" && method === "POST") {
      const body = JSON.parse(String(init?.body)) as { user_id: string; merchant_id: string };
      const match = sessions.find((s) => s.user.id === body.user_id && s.merchant.id === body.merchant_id);
      if (!match) return { status: 403, body: { error: { code: "no_membership", message: "That user is not a member of that business." } } };
      current = match;
      return { status: 200, body: match };
    }
    return undefined;
  };
}
