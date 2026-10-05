import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { AttemptListItem, AttemptListResponse } from "../../api/payments-types";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { ActiveFilters, type Chip } from "../../components/ActiveFilters";
import { DataTable, type Column } from "../../components/DataTable";
import { FilterBar, FilterSearch, FilterSelect } from "../../components/FilterBar";
import { Money } from "../../components/Money";
import { Pagination } from "../../components/Pagination";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import type { QueryState } from "../../lib/query";
import { useSession } from "../../session/SessionProvider";
import { PeriodFilter, periodParams } from "./PeriodFilter";

const PAGE_SIZE = 25;

export function AttemptsTab({ meta, query }: { meta: Meta; query: QueryState }) {
  const navigate = useNavigate();
  const { can } = useSession();
  const sort = query.get("sort", "created_at");
  const dir: "asc" | "desc" = query.get("dir", "desc") === "asc" ? "asc" : "desc";
  const page = query.getInt("page", 1);
  const params = {
    ...periodParams(query),
    q: query.get("q") || undefined,
    outcome: query.get("outcome") || undefined,
    channel: query.get("channel") || undefined,
    location_id: query.get("location_id") || undefined,
    sort,
    dir,
    page,
    page_size: PAGE_SIZE,
  };
  const list = useApi<AttemptListResponse>(`/api/attempts${queryString(params)}`);
  const { page: _page, page_size: _pageSize, ...exportParams } = params;
  const exportHref = `/api/reports/attempts.csv${queryString(exportParams)}`;

  const chips = useMemo<Chip[]>(() => {
    const out: Chip[] = [];
    const label = (options: { value: string; label: string }[], value: string) => options.find((o) => o.value === value)?.label ?? value;
    if (query.get("q")) out.push({ key: "q", label: `Search: ${query.get("q")}`, onRemove: () => query.set({ q: null }) });
    if (query.get("outcome")) out.push({ key: "outcome", label: `Outcome: ${label(meta.attempt_outcomes, query.get("outcome"))}`, onRemove: () => query.set({ outcome: null }) });
    if (query.get("channel")) out.push({ key: "channel", label: `Channel: ${label(meta.channels, query.get("channel"))}`, onRemove: () => query.set({ channel: null }) });
    if (query.get("location_id")) {
      const loc = meta.locations.find((l) => l.id === query.get("location_id"));
      out.push({ key: "location", label: `Location: ${loc?.name ?? "Unknown"}`, onRemove: () => query.set({ location_id: null }) });
    }
    return out;
  }, [query, meta]);

  const columns: Column<AttemptListItem>[] = [
    {
      key: "created_at",
      header: "Attempted",
      sortKey: "created_at",
      render: (a) => (
        <Link to={`/payments/${a.payment_id}`} className="row-link" onClick={(e) => e.stopPropagation()}>
          <Timestamp iso={a.created_at} />
        </Link>
      ),
    },
    { key: "order", header: "Order", sortKey: "order_reference", render: (a) => <span className="mono">{a.order_reference}</span> },
    { key: "attempt", header: "Attempt", render: (a) => <span className="num">#{a.attempt_number}</span> },
    { key: "outcome", header: "Outcome", sortKey: "outcome", render: (a) => <StatusBadge status={a.outcome} label={a.outcome_label} /> },
    { key: "reason", header: "Recorded reason", render: (a) => a.failure_message ?? <span className="muted">—</span> },
    { key: "method", header: "Method", render: (a) => a.method.label },
    { key: "channel", header: "Channel", render: (a) => (a.location ? `${a.channel_label} · ${a.location.name}` : a.channel_label) },
    { key: "customer", header: "Customer", render: (a) => (a.customer ? a.customer.full_name : <span className="muted">Guest</span>) },
    { key: "amount", header: "Amount", align: "right", sortKey: "amount", render: (a) => <Money cents={a.amount_cents} /> },
  ];

  function onSort(key: string) {
    const nextDir = sort === key && dir === "desc" ? "asc" : "desc";
    query.set({ sort: key, dir: nextDir });
  }

  return (
    <>
      <FilterBar
        trailing={
          can("reports:operational") ? (
            <a className="btn" href={exportHref} download data-export="attempts">
              Export CSV
            </a>
          ) : null
        }
      >
        <FilterSearch id="attempts-search" label="Search" value={query.get("q")} placeholder="Order, customer, email or id" onChange={(v) => query.set({ q: v })} />
        <PeriodFilter query={query} presets={meta.period_presets} idPrefix="attempts-period" />
        <FilterSelect id="attempts-outcome" label="Outcome" value={query.get("outcome")} options={meta.attempt_outcomes} onChange={(v) => query.set({ outcome: v })} />
        <FilterSelect
          id="attempts-channel"
          label="Channel"
          value={query.get("channel")}
          options={meta.channels}
          onChange={(v) => query.set({ channel: v, location_id: v === "in_store" ? query.get("location_id") : null })}
        />
        {meta.locations.length > 0 ? (
          <FilterSelect
            id="attempts-location"
            label="Location"
            value={query.get("location_id")}
            options={meta.locations.map((l) => ({ value: l.id, label: l.name }))}
            onChange={(v) => query.set({ location_id: v, channel: v ? "in_store" : query.get("channel") })}
          />
        ) : null}
      </FilterBar>
      <ActiveFilters chips={chips} onClear={() => query.set({ q: null, outcome: null, channel: null, location_id: null })} />
      {list.data ? (
        <p className="list-period muted">
          Showing {list.data.period.label.toLowerCase()}: {list.data.period.range_label}
        </p>
      ) : null}
      {list.error ? <LoadError error={list.error} onRetry={list.reload} /> : null}
      {!list.error && !list.data && list.loading ? <LoadingState rows={8} /> : null}
      {list.data && list.data.items.length === 0 ? <EmptyState title="No attempts match" body="Try a wider period or clear a filter." /> : null}
      {list.data && list.data.items.length > 0 ? (
        <>
          <DataTable
            caption="Payment attempts"
            columns={columns}
            rows={list.data.items}
            rowKey={(a) => a.id}
            sort={{ sort, dir }}
            onSort={onSort}
            onRowClick={(a) => navigate(`/payments/${a.payment_id}`)}
            loading={list.loading}
          />
          <Pagination page={list.data.page} pageSize={list.data.page_size} total={list.data.total} onPage={(p) => query.set({ page: p })} />
        </>
      ) : null}
    </>
  );
}
