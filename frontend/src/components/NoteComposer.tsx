import { useState } from "react";
import { ApiError, apiFetch } from "../api/client";
import type { NoteItem } from "../api/payments-types";

const MAX = 2000;

type Phase = "idle" | "saving" | "saved" | "error";

/** The product's one write: an internal note. Pending, saved and error states are explicit. */
export function NoteComposer({ postPath, onSaved, label }: { postPath: string; onSaved: (note: NoteItem) => void; label: string }) {
  const [body, setBody] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const trimmed = body.trim();
  const canSave = trimmed.length > 0 && trimmed.length <= MAX && phase !== "saving";

  async function save() {
    if (!canSave) return;
    setPhase("saving");
    setMessage(null);
    try {
      const note = await apiFetch<NoteItem>(postPath, { method: "POST", json: { body: trimmed } });
      setBody("");
      setPhase("saved");
      setMessage("Note saved.");
      onSaved(note);
    } catch (cause) {
      setPhase("error");
      setMessage(cause instanceof ApiError ? cause.message : "Could not save the note.");
    }
  }

  return (
    <form
      className="note-composer"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <label className="field" htmlFor="note-body">
        <span className="field-label">{label}</span>
        <textarea
          id="note-body"
          className="input note-textarea"
          rows={3}
          maxLength={MAX}
          value={body}
          placeholder="What did you check, and what did you find?"
          onChange={(e) => {
            setBody(e.target.value);
            if (phase !== "saving") setPhase("idle");
          }}
          disabled={phase === "saving"}
        />
      </label>
      <div className="note-actions">
        <span className="muted num">
          {trimmed.length.toLocaleString("en-US")} / {MAX.toLocaleString("en-US")}
        </span>
        <span className={`note-status${phase === "error" ? " note-status-error" : ""}`} role="status" aria-live="polite">
          {phase === "saving" ? "Saving…" : message}
        </span>
        <button type="submit" className="btn btn-primary" disabled={!canSave} aria-busy={phase === "saving" || undefined}>
          {phase === "saving" ? "Saving…" : "Add note"}
        </button>
      </div>
    </form>
  );
}
