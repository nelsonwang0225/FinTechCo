import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, apiFetch, onUnauthenticated } from "../api/client";
import type { Permission, Session } from "../api/types";

export type SessionStatus = "loading" | "anonymous" | "ready";

export interface SessionContextValue {
  status: SessionStatus;
  session: Session | null;
  can: (permission: Permission) => boolean;
  signIn: (userId: string, merchantId: string) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [session, setSession] = useState<Session | null>(null);

  const refresh = useCallback(async () => {
    try {
      const current = await apiFetch<Session>("/api/session");
      setSession(current);
      setStatus("ready");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        setSession(null);
        setStatus("anonymous");
        return;
      }
      throw cause;
    }
  }, []);

  useEffect(() => {
    void refresh().catch(() => {
      setSession(null);
      setStatus("anonymous");
    });
    return onUnauthenticated(() => {
      setSession(null);
      setStatus("anonymous");
    });
  }, [refresh]);

  const signIn = useCallback(async (userId: string, merchantId: string) => {
    const next = await apiFetch<Session>("/api/dev/session", { method: "POST", json: { user_id: userId, merchant_id: merchantId } });
    setSession(next);
    setStatus("ready");
  }, []);

  const signOut = useCallback(async () => {
    await apiFetch<void>("/api/session", { method: "DELETE" });
    setSession(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      status,
      session,
      can: (permission) => session?.permissions.includes(permission) ?? false,
      signIn,
      signOut,
      refresh,
    }),
    [status, session, signIn, signOut, refresh],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}

/** The current session, for product pages that only render once signed in. */
export function useCurrentSession(): Session {
  const { session } = useSession();
  if (!session) throw new Error("no active session");
  return session;
}
