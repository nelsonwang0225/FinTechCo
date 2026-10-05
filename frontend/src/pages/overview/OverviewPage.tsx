import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { AttentionItem, Overview } from "../../api/overview-types";
import type { PaymentListItem } from "../../api/payments-types";
import type { Meta, Permission } from "../../api/types";
import { useApi } from "../../api/useApi";
import { BarChart } from "../../components/BarChart";
import { DataTable, type Column } from "../../components/DataTable";
import { FilterBar } from "../../components/FilterBar";
import { Money } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { daysUntil, formatCents, formatDateShort, formatTimestampFull, formatWeekdayDate } from "../../lib/format";
import { useQueryState } from "../../lib/query";
import { useSession } from "../../session/SessionProvider";
import { PeriodFilter, periodParams } from "../payments/PeriodFilter";

export function OverviewPage() {
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const overview = useApi<Overview>(`/api/overview${queryString(periodParams(query))}`);
  const data = overview.data;

  return (
    <>
      <PageHeader
        title={data ? `${data.greeting.salutation}, ${data.greeting.first_name}` : "Overview"}
        subtitle={data ? `${data.greeting.merchant_name} · As of ${formatTimestampFull(data.greeting.as_of)}` : undefined}
      />
      {meta.data ? (
        <FilterBar>
          <PeriodFilter query={query} presets={meta.data.period_presets} idPrefix="overview-period" />
        </FilterBar>
      ) : null}
      {overview.error ? <LoadError error={overview.error} onRetry={overview.reload} /> : null}
      {!overview.error && !data ? <LoadingState rows={8} /> : null}
      {data ? <OverviewBody data={data} loading={overview.loading} /> : null}
    </>
  );
}

function OverviewBody({ data, loading }: { data: Overview; loading: boolean }) {
  const { can } = useSession();
  const periodFoot = `${data.period.label} · ${data.period.range_label}`;
  const chartSeries = data.chart.points.map((p) => ({ label: formatDateShort(p.day), value: p.amount_cents }));
  return (
    <div className={loading ? "overview overview-loading" : "overview"} aria-busy={loading || undefined}>
      <div className="cards cards-4">
        <section className="card stat-card" aria-label="Gross collected">
          <p className="stat-label">Gross collected</p>
          <p className="stat-value">
            <Money cents={data.tiles.collected_cents} />
          </p>
          <p className="stat-foot">{periodFoot}</p>
        </section>
        <section className="card stat-card" aria-label="Refunds processed">
          <p className="stat-label">Refunds processed</p>
          <p className="stat-value">
            <Money cents={data.tiles.refunds_cents} />
          </p>
          <p className="stat-foot">{periodFoot}</p>
        </section>
        <section className="card stat-card" aria-label="Funds available for payout">
          <p className="stat-label">Funds available for payout</p>
          <p className="stat-value">
            <Money cents={data.tiles.funds_available_cents} />
          </p>
          <p className="stat-foot">As of {formatTimestampFull(data.greeting.as_of)}</p>
        </section>
        <section className="card stat-card" aria-label="Next payout">
          <p className="stat-label">Next payout · {formatWeekdayDate(data.tiles.next_payout.payout_date)}</p>
          <p className="stat-value">
            <Money cents={data.tiles.next_payout.amount_cents} />
          </p>
          <p className="stat-foot">{data.tiles.next_payout.note}</p>
          {can("payouts:read") ? (
            <p className="stat-foot">
              <Link to="/payouts">View payouts</Link>
            </p>
          ) : null}
        </section>
      </div>

      <section className="card chart-card" aria-labelledby="chart-heading">
        <div className="section-head">
          <h2 id="chart-heading" className="section-title">
            {data.chart.title}
          </h2>
          <p className="muted section-aside">
            {formatCents(data.chart.total_cents)} collected · {data.period.range_label}
          </p>
        </div>
        <BarChart title={`${data.chart.title}, ${data.period.range_label}`} series={chartSeries} formatValue={(v) => formatCents(v)} formatTick={wholeDollars} />
      </section>

      <div className="overview-grid">
        <section aria-labelledby="recent-heading">
          <div className="section-head">
            <h2 id="recent-heading" className="section-title">
              Recent payments
            </h2>
            <Link to="/payments" className="section-aside">
              All payments
            </Link>
          </div>
          <RecentPayments items={data.recent_payments} />
        </section>
        <div className="detail-stack">
          <section className="card" aria-labelledby="upcoming-heading">
            <h2 id="upcoming-heading" className="section-title">
              Upcoming payout · {formatWeekdayDate(data.upcoming_payout.payout_date)}
            </h2>
            <p className="stat-value">
              <Money cents={data.upcoming_payout.amount_cents} />
            </p>
            <p className="stat-foot">
              {data.upcoming_payout.schedule_label} · {data.upcoming_payout.note}
            </p>
            <dl className="bucket-list">
              <BucketRow label="Collections" cents={data.upcoming_payout.buckets.collections_cents} />
              <BucketRow label="Fees" cents={data.upcoming_payout.buckets.fees_cents} />
              <BucketRow label="Refunds" cents={data.upcoming_payout.buckets.refunds_cents} />
              <BucketRow label="Disputes" cents={data.upcoming_payout.buckets.disputes_cents} />
              <BucketRow label="Adjustments" cents={data.upcoming_payout.buckets.adjustments_cents} />
            </dl>
            <p className="stat-foot muted">{data.upcoming_payout.destination}</p>
          </section>
          <section className="card" aria-labelledby="attention-heading">
            <h2 id="attention-heading" className="section-title">
              Needs attention
            </h2>
            <AttentionList items={data.attention} asOf={data.greeting.as_of} can={can} />
          </section>
        </div>
      </div>
    </div>
  );
}

/** Gridline labels read better without cents; every tick is a whole-dollar amount. */
function wholeDollars(cents: number): string {
  return formatCents(cents).replace(/\.00$/, "");
}

function BucketRow({ label, cents }: { label: string; cents: number }) {
  return (
    <div className="bucket-row">
      <dt>{label}</dt>
      <dd className="money">
        <Money cents={cents} sign />
      </dd>
    </div>
  );
}

function RecentPayments({ items }: { items: PaymentListItem[] }) {
  const navigate = useNavigate();
  const columns: Column<PaymentListItem>[] = [
    {
      key: "created_at",
      header: "Created",
      render: (p) => (
        <Link to={`/payments/${p.id}`} className="row-link" onClick={(e) => e.stopPropagation()}>
          <Timestamp iso={p.created_at} />
        </Link>
      ),
    },
    { key: "order", header: "Order", render: (p) => <span className="mono">{p.order_reference}</span> },
    { key: "customer", header: "Customer", render: (p) => (p.customer ? p.customer.full_name : <span className="muted">Guest</span>) },
    { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} label={p.status_label} /> },
    { key: "amount", header: "Amount", align: "right", render: (p) => <Money cents={p.amount_cents} /> },
  ];
  if (items.length === 0) return <EmptyState title="No payments yet" body="Payments appear here as soon as they are created." />;
  return <DataTable caption="Recent payments" columns={columns} rows={items} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/payments/${p.id}`)} />;
}

function attentionPath(item: AttentionItem): string {
  switch (item.link.kind) {
    case "dispute":
      return `/disputes/${item.link.id}`;
    case "payout":
      return `/payouts/${item.link.id}`;
    default:
      return `/payments/${item.link.id}`;
  }
}

function dueText(item: AttentionItem, asOf: string): string | null {
  if (item.kind !== "dispute_deadline") return null;
  const days = daysUntil(item.at, asOf);
  if (days < 0) return `Overdue by ${-days} day${days === -1 ? "" : "s"}`;
  if (days === 0) return "Due today";
  return `Due in ${days} day${days === 1 ? "" : "s"}`;
}

function AttentionList({ items, asOf, can }: { items: AttentionItem[]; asOf: string; can: (permission: Permission) => boolean }) {
  if (items.length === 0) return <p className="muted attention-empty">Nothing needs attention right now.</p>;
  return (
    <ul className="attention-list">
      {items.map((item) => {
        const due = dueText(item, asOf);
        return (
          <li key={`${item.kind}-${item.link.id}`} className={`attention-item attention-${item.kind}`}>
            <span className="attention-dot" aria-hidden="true" />
            <div className="attention-body">
              <p className="attention-title">{can(item.link.permission) ? <Link to={attentionPath(item)}>{item.title}</Link> : item.title}</p>
              <p className="attention-detail muted">{item.detail}</p>
              <p className="attention-when">
                {due ? <strong>{due}</strong> : null}
                {due ? " · " : null}
                {item.at_label} <Timestamp iso={item.at} />
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
