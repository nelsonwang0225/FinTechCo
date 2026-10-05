import type { Option } from "../../api/types";
import { FilterDate, FilterSelect } from "../../components/FilterBar";
import type { QueryState } from "../../lib/query";

/**
 * Period preset plus custom Chicago dates, all in the URL. The API resolves presets against the reporting clock;
 * this component never computes a date itself.
 */
export function PeriodFilter({ query, presets, idPrefix = "period" }: { query: QueryState; presets: Option[]; idPrefix?: string }) {
  const preset = query.get("period", query.get("from") || query.get("to") ? "custom" : "last_7_days");
  return (
    <>
      <FilterSelect
        id={`${idPrefix}-preset`}
        label="Period"
        value={preset}
        options={presets}
        allLabel={null}
        onChange={(value) => {
          if (value === "custom") query.set({ period: "custom" });
          else query.set({ period: value, from: null, to: null });
        }}
      />
      {preset === "custom" ? (
        <>
          <FilterDate id={`${idPrefix}-from`} label="From" value={query.get("from")} max={query.get("to") || undefined} onChange={(v) => query.set({ period: "custom", from: v })} />
          <FilterDate id={`${idPrefix}-to`} label="To" value={query.get("to")} min={query.get("from") || undefined} onChange={(v) => query.set({ period: "custom", to: v })} />
        </>
      ) : null}
    </>
  );
}

/** Query-string pieces for the API from the URL period state. Incomplete custom dates fall back to the default preset. */
export function periodParams(query: QueryState): Record<string, string | undefined> {
  const preset = query.get("period");
  const from = query.get("from");
  const to = query.get("to");
  if (preset === "custom" || (!preset && (from || to))) {
    if (from && to) return { period: "custom", from, to };
    return { period: "last_7_days" };
  }
  return { period: preset || "last_7_days" };
}
