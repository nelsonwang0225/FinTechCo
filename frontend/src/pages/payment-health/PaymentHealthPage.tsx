import { Link } from "react-router-dom";
import { queryString } from "../../api/client";
import type { ChannelHealth, FailureSignal, PaymentHealth } from "../../api/payment-health-types";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { FilterBar, FilterSelect } from "../../components/FilterBar";
import { Money } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { formatCount, formatPoints, formatRate } from "../../lib/format";
import { useQueryState, type QueryState } from "../../lib/query";
import { PeriodFilter, periodParams } from "../payments/PeriodFilter";

/** The Payments list showing a scope's unresolved payments: derived status failed, same dates, same channel. */
export function unresolvedPaymentsHref(query: QueryState, channel: string | null): string {
  return `/payments${queryString({ ...periodParams(query), channel: channel || undefined, status: "failed" })}`;
}

export function PaymentHealthPage() {
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const channel = query.get("channel");
  const health = useApi<PaymentHealth>(`/api/payment-health${queryString({ ...periodParams(query), channel: channel || undefined })}`);

  return (
    <>
      <PageHeader
        title="Payment health"
        subtitle="Completed-attempt success by channel, compared with each channel's own baseline. Dates are America/Chicago calendar days."
        actions={
          meta.data ? (
            <FilterBar>
              <PeriodFilter query={query} presets={meta.data.period_presets} idPrefix="health-period" />
              <FilterSelect id="health-channel" label="Channel" value={channel} options={meta.data.channels} allLabel="All channels" onChange={(v) => query.set({ channel: v })} />
            </FilterBar>
          ) : undefined
        }
      />
      {health.error ? <LoadError error={health.error} onRetry={health.reload} /> : null}
      {!health.error && !health.data ? <LoadingState rows={8} label="Loading payment health" /> : null}
      {health.data ? <HealthBody data={health.data} query={query} loading={health.loading} /> : null}
    </>
  );
}

function HealthBody({ data, query, loading }: { data: PaymentHealth; query: QueryState; loading: boolean }) {
  const k = data.kpis;
  return (
    <div className={loading ? "health health-loading" : "health"} aria-busy={loading || undefined}>
      <div className="toolbar-note">
        <span>
          {data.channel_label} · {data.period.label}: {data.period.range_label}, compared with the {data.rules.baseline_days} days before ({data.baseline.range_label})
        </span>
      </div>

      <AttentionCard data={data} query={query} />

      <div className="cards cards-4">
        <section className="card stat-card" aria-label="Success rate">
          <p className="stat-label">Success rate</p>
          <p className="stat-value">{formatRate(k.rate_bp)}</p>
          {k.rate_bp === null ? (
            <p className="stat-foot">No completed attempts in this period</p>
          ) : k.baseline_completed < data.rules.min_baseline_completed ? (
            <p className="stat-foot">
              Baseline has {formatCount(k.baseline_completed)} completed attempts, too few to compare
            </p>
          ) : (
            <p className="stat-foot">
              Baseline {formatRate(k.baseline_rate_bp)} · {formatPoints(k.delta_bp)}
            </p>
          )}
          <p className="stat-foot">
            {formatCount(k.completed)} completed · {formatCount(k.pending)} pending not counted
          </p>
        </section>
        <section className="card stat-card" aria-label="Failed attempts">
          <p className="stat-label">Failed attempts</p>
          <p className="stat-value num">{formatCount(k.failed)}</p>
          <p className="stat-foot">of {formatCount(k.completed)} completed attempts</p>
        </section>
        <section className="card stat-card" aria-label="Affected payments">
          <p className="stat-label">Affected payments</p>
          <p className="stat-value num">{formatCount(k.affected_payments)}</p>
          <p className="stat-foot">
            {formatCount(k.recovered_payments)} recovered · {formatCount(k.unresolved_payments)} unresolved
            {k.awaiting_retry_payments > 0 ? ` · ${formatCount(k.awaiting_retry_payments)} awaiting retry` : ""}
          </p>
          {k.unresolved_payments > 0 ? (
            <p className="stat-foot">
              <Link to={unresolvedPaymentsHref(query, data.channel)}>Review unresolved payments</Link>
            </p>
          ) : null}
        </section>
        <section className="card stat-card" aria-label="Affected value">
          <p className="stat-label">Affected value</p>
          <p className="stat-value">
            <Money cents={k.affected_cents} />
          </p>
          <p className="stat-foot">Payment amounts, each affected payment counted once</p>
        </section>
      </div>

      <section className="card health-section" aria-labelledby="channels-heading">
        <div className="section-head">
          <h2 id="channels-heading" className="section-title">
            Performance by channel
          </h2>
          <p className="muted section-aside">
            Degraded at {formatPoints(data.rules.degraded_drop_bp, { signed: false })} below baseline · needs {data.rules.min_period_completed} completed attempts in the period and{" "}
            {data.rules.min_baseline_completed} in the baseline
          </p>
        </div>
        <ChannelTable channels={data.channels} />
      </section>

      <section className="card health-section" aria-labelledby="signals-heading">
        <div className="section-head">
          <h2 id="signals-heading" className="section-title">
            Recorded failure signals
          </h2>
          <p className="muted section-aside">As recorded on failed attempts, not confirmed root causes</p>
        </div>
        <SignalTable signals={data.failure_signals} failed={k.failed} />
      </section>
    </div>
  );
}

function AttentionCard({ data, query }: { data: PaymentHealth; query: QueryState }) {
  const { state, message, degraded } = data.summary;
  return (
    <section className={`card health-summary health-summary-${state}`} aria-labelledby="attention-heading">
      <h2 id="attention-heading" className="section-title">
        {state === "degraded" ? "Degradation detected" : state === "no_degradation" ? "No significant degradation detected" : "Not enough volume to evaluate"}
      </h2>
      <p className="health-summary-message">{message}</p>
      {degraded.length > 0 ? (
        <ul className="health-degraded-list">
          {degraded.map((c) => (
            <li key={c.channel}>
              <StatusBadge status={c.evaluation} label={c.channel_label} />
              <span className="num">
                {formatRate(c.rate_bp)} vs {formatRate(c.baseline_rate_bp)} baseline ({formatPoints(c.delta_bp)}) · {formatCount(c.failed)} failed attempts
              </span>
              <Link to={unresolvedPaymentsHref(query, c.channel)}>Review unresolved {c.channel_label.toLowerCase()} payments</Link>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function ChannelTable({ channels }: { channels: ChannelHealth[] }) {
  if (channels.length === 0) return <EmptyState title="No attempts in this period or its baseline" body="Try a wider period." />;
  const columns: Column<ChannelHealth>[] = [
    { key: "channel", header: "Channel", className: "primary", render: (c) => c.channel_label },
    { key: "evaluation", header: "Evaluation", render: (c) => <StatusBadge status={c.evaluation} label={c.evaluation_label} /> },
    { key: "rate", header: "Success rate", align: "right", render: (c) => formatRate(c.rate_bp) },
    { key: "baseline", header: "Baseline", align: "right", render: (c) => formatRate(c.baseline_rate_bp) },
    { key: "delta", header: "Change", align: "right", render: (c) => formatPoints(c.delta_bp) },
    { key: "completed", header: "Completed", align: "right", render: (c) => formatCount(c.completed) },
    { key: "failed", header: "Failed", align: "right", render: (c) => formatCount(c.failed) },
    { key: "pending", header: "Pending", align: "right", render: (c) => formatCount(c.pending) },
    { key: "baseline_completed", header: "Baseline completed", align: "right", render: (c) => formatCount(c.baseline_completed) },
  ];
  return <DataTable caption="Performance by channel" columns={columns} rows={channels} rowKey={(c) => c.channel} />;
}

/** Share of failed attempts in basis points, rounded half-up with integer arithmetic. */
function shareBp(count: number, failed: number): number | null {
  if (failed === 0) return null;
  return Math.floor((count * 20000 + failed) / (failed * 2));
}

function SignalTable({ signals, failed }: { signals: FailureSignal[]; failed: number }) {
  if (signals.length === 0) return <EmptyState title="No failed attempts in this period" body="There are no recorded failure signals to break down." />;
  const columns: Column<FailureSignal>[] = [
    { key: "label", header: "Recorded signal", className: "primary", render: (s) => s.label },
    { key: "code", header: "Code", className: "secondary", render: (s) => <span className="mono">{s.code}</span> },
    { key: "count", header: "Failed attempts", align: "right", render: (s) => formatCount(s.count) },
    { key: "share", header: "Share of failed", align: "right", render: (s) => formatRate(shareBp(s.count, failed)) },
  ];
  return <DataTable caption="Recorded failure signals" columns={columns} rows={signals} rowKey={(s) => s.code} />;
}
