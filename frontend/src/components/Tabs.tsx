export interface TabDef {
  id: string;
  label: string;
}

/** A tablist whose active tab lives in the URL (the parent owns the state). */
export function Tabs({ tabs, active, onChange, label }: { tabs: TabDef[]; active: string; onChange: (id: string) => void; label: string }) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={`panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            className={`tab${selected ? " active" : ""}`}
            onClick={() => onChange(tab.id)}
            onKeyDown={(e) => {
              const index = tabs.findIndex((t) => t.id === active);
              const next = tabs[(index + 1) % tabs.length];
              const prev = tabs[(index - 1 + tabs.length) % tabs.length];
              const target = e.key === "ArrowRight" ? next : e.key === "ArrowLeft" ? prev : undefined;
              if (!target) return;
              e.preventDefault();
              onChange(target.id);
              document.getElementById(`tab-${target.id}`)?.focus();
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
