import { useEffect, useState, type ReactNode } from "react";
import type { Option } from "../api/types";

export function FilterBar({ children, trailing }: { children: ReactNode; trailing?: ReactNode }) {
  return (
    <div className="filterbar" role="group" aria-label="Filters">
      <div className="filterbar-fields">{children}</div>
      {trailing ? <div className="filterbar-trailing">{trailing}</div> : null}
    </div>
  );
}

export function FilterSelect({ id, label, value, options, onChange, allLabel = "All" }: {
  id: string;
  label: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
  allLabel?: string | null;
}) {
  return (
    <label className="field" htmlFor={id}>
      <span className="field-label">{label}</span>
      <select id={id} className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {allLabel !== null ? <option value="">{allLabel}</option> : null}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/** A search box that commits on Enter or after a short pause, so the URL does not churn on every keystroke. */
export function FilterSearch({ id, label, value, onChange, placeholder }: { id: string; label: string; value: string; onChange: (value: string) => void; placeholder?: string }) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  useEffect(() => {
    if (draft === value) return;
    const handle = setTimeout(() => onChange(draft), 350);
    return () => clearTimeout(handle);
  }, [draft, value, onChange]);
  return (
    <label className="field field-search" htmlFor={id}>
      <span className="field-label">{label}</span>
      <input
        id={id}
        type="search"
        className="input"
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onChange(draft);
        }}
      />
    </label>
  );
}

export function FilterDate({ id, label, value, onChange, min, max }: { id: string; label: string; value: string; onChange: (value: string) => void; min?: string; max?: string }) {
  return (
    <label className="field" htmlFor={id}>
      <span className="field-label">{label}</span>
      <input id={id} type="date" className="input" value={value} min={min} max={max} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
