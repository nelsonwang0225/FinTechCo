export interface Chip {
  key: string;
  label: string;
  onRemove: () => void;
}

/** The filters currently narrowing a list, each removable. */
export function ActiveFilters({ chips, onClear }: { chips: Chip[]; onClear: () => void }) {
  if (chips.length === 0) return null;
  return (
    <div className="chips" aria-label="Active filters">
      {chips.map((chip) => (
        <span key={chip.key} className="chip">
          {chip.label}
          <button type="button" className="chip-remove" onClick={chip.onRemove} aria-label={`Remove filter ${chip.label}`}>
            ×
          </button>
        </span>
      ))}
      <button type="button" className="chip-clear" onClick={onClear}>
        Clear all
      </button>
    </div>
  );
}
