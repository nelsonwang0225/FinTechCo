import { useState } from "react";
import { ApiError } from "../api/client";
import type { PersonasResponse } from "../api/types";
import { useApi } from "../api/useApi";
import { useCurrentSession, useSession } from "../session/SessionProvider";

/** Collapsible dark band above the product chrome: who you are, switch persona, sign out. Development only. */
export function PersonaBar() {
  const session = useCurrentSession();
  const { signIn, signOut } = useSession();
  const [open, setOpen] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const personas = useApi<PersonasResponse>(open ? "/api/dev/personas" : null);

  async function switchTo(value: string) {
    const [userId, merchantId] = value.split("|");
    if (!userId || !merchantId) return;
    setBusy(true);
    setError(null);
    try {
      await signIn(userId, merchantId);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not switch persona.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="dev-bar dev-bar-collapsed">
        <span className="dev-bar-label">Development</span>
        <span className="dev-bar-who">
          {session.user.full_name} · {session.role_label} · {session.merchant.name}
        </span>
        <button type="button" className="dev-bar-btn" onClick={() => setOpen(true)}>
          Show persona tools
        </button>
      </div>
    );
  }

  const current = `${session.user.id}|${session.merchant.id}`;
  return (
    <div className="dev-bar" role="region" aria-label="Development persona tools">
      <span className="dev-bar-label">Development</span>
      <span className="dev-bar-who">
        Signed in as <strong>{session.user.full_name}</strong> ({session.role_label}) at <strong>{session.merchant.name}</strong>
      </span>
      <label className="dev-bar-field" htmlFor="persona-switch">
        <span>Switch persona</span>
        <select id="persona-switch" value={current} disabled={busy || !personas.data} onChange={(e) => void switchTo(e.target.value)}>
          {personas.data?.merchants.map((group) => (
            <optgroup key={group.merchant.id} label={group.merchant.name}>
              {group.personas.map((p) => (
                <option key={p.membership_id} value={`${p.user_id}|${group.merchant.id}`}>
                  {p.full_name} — {p.role_label}
                </option>
              ))}
            </optgroup>
          )) ?? <option value={current}>{session.user.full_name}</option>}
        </select>
      </label>
      <button type="button" className="dev-bar-btn" disabled={busy} onClick={() => void signOut()}>
        Sign out
      </button>
      <button type="button" className="dev-bar-btn" onClick={() => setOpen(false)}>
        Hide
      </button>
      {error ? (
        <span className="dev-bar-error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}
