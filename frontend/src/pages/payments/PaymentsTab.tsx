import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { PaymentListItem, PaymentListResponse } from "../../api/payments-types";
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
import { formatCents, parseDollarsToCents } from "../../lib/format";
import type { QueryState } from "../../lib/query";
import { PeriodFilter, periodParams } from "./PeriodFilter";

const PAGE_SIZE = 25;

export function PaymentsTab({ meta, query }: { meta: Meta; query: QueryState }) {
  const navigate = useNavigate();
  const sort = query.get("sort", "created_at");
  const dir: "asc" | "desc" = query.get("dir", "desc") === "asc" ? "asc" : "desc";
  const page = query.getInt("page", 1);
  const params = {
    ...periodParams(query),
    q: query.get("q") || undefined,
    status: query.get("status") || undefined,
    channel: query.get("channel") || undefined,
    location_id: query.get("location_id") || undefined,
    amount_min_cents: query.get("amount_min_cents") || undefined,
    amount_max_cents: query.get("amount_max_cents") || undefined,
    sort,
    dir,
    page,
    page_size: PAGE_SIZE,
  };
  const list = useApi<PaymentListResponse>(`/api/payments${queryString(params)}`);

  const chips = useMemo<Chip[]>(() => {
    const out: Chip[] = [];
    const label = (options: { value: string; label: string }[], value: string) => options.find((o) => o.value === value)?.label ?? value;
    if (query.get("q")) out.push({ key: "q", label: `Search: ${query.get("q")}`, onRemove: () => query.set({ q: null }) });
    if (query.get("status")) out.push({ key: "status", label: `Status: ${label(meta.payment_statuses, query.get("status"))}`, onRemove: () => query.set({ status: null }) });
    if (query.get("channel")) out.push({ key: "channel", label: `Channel: ${label(meta.channels, query.get("channel"))}`, onRemove: () => query.set({ channel: null }) });
    if (query.get("location_id")) {
      const loc = meta.locations.find((l) => l.id === query.get("location_id"));
      out.push({ key: "location", label: `Location: ${loc?.name ?? "Unknown"}`, onRemove: () => query.set({ location_id: null }) });
    }
    if (query.get("amount_min_cents")) out.push({ key: "min", label: `Min ${formatCents(Number(query.get("amount_min_cents")))}`, onRemove: () => query.set({ amount_min_cents: null }) });
    if (query.get("amount_max_cents")) out.push({ key: "max", label: `Max ${formatCents(Number(query.get("amount_max_cents")))}`, onRemove: () => query.set({ amount_max_cents: null }) });
    return out;
  }, [query, meta]);

  const columns: Column<PaymentListItem>[] = [
    {
      key: "created_at",
      header: "Created",
      sortKey: "created_at",
      render: (p) => (
        <Link to={`/payments/${p.id}`} className="row-link" onClick={(e) => e.stopPropagation()}>
          <Timestamp iso={p.created_at} />
        </Link>
      ),
    },
    { key: "order", header: "Order", sortKey: "order_reference", render: (p) => <span className="mono">{p.order_reference}</span> },
    { key: "customer", header: "Customer", sortKey: "customer", render: (p) => (p.customer ? p.customer.full_name : <span className="muted">Guest</span>) },
    { key: "status", header: "Status", sortKey: "status", render: (p) => <StatusBadge status={p.status} label={p.status_label} /> },
    { key: "channel", header: "Channel", render: (p) => (p.location ? `${p.channel_label} · ${p.location.name}` : p.channel_label) },
    { key: "method", header: "Method", render: (p) => p.method?.label ?? <span className="muted">—</span> },
    { key: "dispute", header: "", render: (p) => (p.dispute_id ? <StatusBadge status={p.dispute_status ?? "needs_response"} label="Disputed" /> : null) },
    { key: "amount", header: "Amount", align: "right", sortKey: "amount", render: (p) => <Money cents={p.amount_cents} /> },
  ];

  function onSort(key: string) {
    const nextDir = sort === key && dir === "desc" ? "asc" : "desc";
    query.set({ sort: key, dir: nextDir });
  }

  return (
    <>
      <FilterBar>
        <FilterSearch id="payments-search" label="Search" value={query.get("q")} placeholder="Order, customer, email or payment id" onChange={(v) => query.set({ q: v })} />
        <PeriodFilter query={query} presets={meta.period_presets} />
        <FilterSelect id="payments-status" label="Status" value={query.get("status")} options={meta.payment_statuses} onChange={(v) => query.set({ status: v })} />
        <FilterSelect
          id="payments-channel"
          label="Channel"
          value={query.get("channel")}
          options={meta.channels}
          onChange={(v) => query.set({ channel: v, location_id: v === "in_store" ? query.get("location_id") : null })}
        />
        {meta.locations.length > 0 ? (
          <FilterSelect
            id="payments-location"
            label="Location"
            value={query.get("location_id")}
            options={meta.locations.map((l) => ({ value: l.id, label: l.name }))}
            onChange={(v) => query.set({ location_id: v, channel: v ? "in_store" : query.get("channel") })}
          />
        ) : null}
        <AmountInput id="payments-min" label="Min amount" cents={query.get("amount_min_cents")} onChange={(c) => query.set({ amount_min_cents: c })} />
        <AmountInput id="payments-max" label="Max amount" cents={query.get("amount_max_cents")} onChange={(c) => query.set({ amount_max_cents: c })} />
      </FilterBar>
      <ActiveFilters chips={chips} onClear={() => query.set({ q: null, status: null, channel: null, location_id: null, amount_min_cents: null, amount_max_cents: null })} />
      {list.data ? (
        <p className="list-period muted">
          Showing {list.data.period.label.toLowerCase()}: {list.data.period.range_label}
        </p>
      ) : null}
      {list.error ? <LoadError error={list.error} onRetry={list.reload} /> : null}
      {!list.error && !list.data && list.loading ? <LoadingState rows={8} /> : null}
      {list.data && list.data.items.length === 0 ? <EmptyState title="No payments match" body="Try a wider period or clear a filter." /> : null}
      {list.data && list.data.items.length > 0 ? (
        <>
          <DataTable
            caption="Payments"
            columns={columns}
            rows={list.data.items}
            rowKey={(p) => p.id}
            sort={{ sort, dir }}
            onSort={onSort}
            onRowClick={(p) => navigate(`/payments/${p.id}`)}
            loading={list.loading}
          />
          <Pagination page={list.data.page} pageSize={list.data.page_size} total={list.data.total} onPage={(p) => query.set({ page: p })} />
        </>
      ) : null}
    </>
  );
}

/** Dollars typed by a person, stored in the URL as integer cents. Parsing is integer arithmetic, never a float. */
function AmountInput({ id, label, cents, onChange }: { id: string; label: string; cents: string; onChange: (cents: number | null) => void }) {
  const display = cents ? formatCents(Number(cents), { symbol: false }).replace(/,/g, "") : "";
  return (
    <label className="field field-amount" htmlFor={id}>
      <span className="field-label">{label}</span>
      <input
        id={id}
        className="input"
        inputMode="decimal"
        placeholder="0.00"
        defaultValue={display}
        key={display}
        onBlur={(e) => {
          const parsed = parseDollarsToCents(e.target.value);
          if (e.target.value.trim() === "") onChange(null);
          else if (parsed !== null && parsed >= 0) onChange(parsed);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
      />
    </label>
  );
}
