import { useState } from "react";
import { ApiError } from "../api/client";
import type { PersonasResponse } from "../api/types";
import { useApi } from "../api/useApi";
import { useSession } from "../session/SessionProvider";

/** Full-screen development-only persona picker. Deliberately styled as a tool, not as product UI. */
export function PersonaChooser() {
  const { signIn } = useSession();
  const personas = useApi<PersonasResponse>("/api/dev/personas");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function choose(userId: string, merchantId: string, membershipId: string) {
    setBusy(membershipId);
    setError(null);
    try {
      await signIn(userId, merchantId);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not start that session.");
      setBusy(null);
    }
  }

  return (
    <div className="dev-chooser">
      <div className="dev-chooser-panel">
        <p className="dev-kicker">Development · persona selector</p>
        <h1 className="dev-title">Choose who you are</h1>
        <p className="dev-lede">
          Pick a seeded team member to open FinTechCo Business as them. The server checks that the person belongs to the business; the
          session carries only that membership.
        </p>
        {personas.loading ? <p className="dev-muted">Loading personas…</p> : null}
        {personas.error ? <p className="dev-error" role="alert">{personas.error.message}</p> : null}
        {error ? (
          <p className="dev-error" role="alert">
            {error}
          </p>
        ) : null}
        {personas.data?.merchants.map((group) => (
          <section key={group.merchant.id} className="dev-group" aria-labelledby={`dev-group-${group.merchant.slug}`}>
            <h2 id={`dev-group-${group.merchant.slug}`} className="dev-group-title">
              {group.merchant.name}
            </h2>
            <ul className="dev-list">
              {group.personas.map((p) => (
                <li key={p.membership_id}>
                  <button
                    type="button"
                    className="dev-persona"
                    disabled={busy !== null}
                    aria-busy={busy === p.membership_id || undefined}
                    onClick={() => void choose(p.user_id, group.merchant.id, p.membership_id)}
                  >
                    <span className="dev-persona-name">{p.full_name}</span>
                    <span className="dev-persona-role">{p.role_label}</span>
                    <span className="dev-persona-title">{p.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
        <p className="dev-foot">Demo environment · Synthetic data. Every business, person and transaction here is fictional.</p>
      </div>
    </div>
  );
}
