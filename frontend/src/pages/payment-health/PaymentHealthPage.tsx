import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { ChannelHealth, FailureSignal, PaymentHealth, UnresolvedPayment } from "../../api/payment-health-types";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { FilterBar, FilterSelect } from "../../components/FilterBar";
import { Money } from "../../components/Money";
import { RateChart } from "../../components/RateChart";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { formatBps, formatBpsChange, formatCount, formatDateShort, formatTimestampFull } from "../../lib/format";
import { useQueryState, type QueryState } from "../../lib/query";
import { PeriodFilter } from "../payments/PeriodFilter";
import { attemptsHref, healthScope, unresolvedHref, type HealthScope } from "./links";

export function PaymentHealthPage() {
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const scope = healthScope(query);
  const health = useApi<PaymentHealth>(`/api/payment-health${queryString({ ...scope })}`);
  const data = health.data;

  return (
    <>
      <PageHeader
        title="Payment Health"
        subtitle={
          data
            ? `Completed-attempt performance and recovery · As of ${formatTimestampFull(data.as_of)} · Times in America/Chicago`
            : "Completed-attempt performance and recovery. Times are shown in America/Chicago."
        }
        actions={
          meta.data ? (
            <FilterBar>
              <PeriodFilter query={query} presets={meta.data.period_presets} idPrefix="health-period" />
              <FilterSelect id="health-channel" label="Channel" value={query.get("channel")} options={meta.data.channels} allLabel="All channels" onChange={(v) => query.set({ channel: v })} />
            </FilterBar>
          ) : undefined
        }
      />
      {health.error ? <LoadError error={health.error} onRetry={health.reload} /> : null}
      {!health.error && !data ? <LoadingState rows={8} label="Loading payment health" /> : null}
      {data ? <HealthBody data={data} scope={scope} query={query} loading={health.loading} /> : null}
    </>
  );
}

function HealthBody({ data, scope, query, loading }: { data: PaymentHealth; scope: HealthScope; query: QueryState; loading: boolean }) {
  const period = data.scope.period;
  const baseline = data.scope.baseline;
  const periodFoot = `${data.period.label} · ${data.period.range_label}`;
  return (
    <div className={loading ? "health health-loading" : "health"} aria-busy={loading || undefined}>
      <AttentionSummary data={data} scope={scope} />

      <div className="cards cards-4">
        <section className="card stat-card" aria-label="Success rate">
          <p className="stat-label">Success rate</p>
          <p className="stat-value">{formatBps(period.success_rate_bps)}</p>
          <p className="stat-foot">
            Baseline {formatBps(baseline.success_rate_bps)} · {formatBpsChange(data.scope.change_bps)}
          </p>
        </section>
        <section className="card stat-card" aria-label="Failed attempts">
          <p className="stat-label">Failed attempts</p>
          <p className="stat-value">{formatCount(period.failed)}</p>
          <p className="stat-foot">{formatBps(period.failure_rate_bps)} of completed attempts</p>
        </section>
        <section className="card stat-card" aria-label="Completed attempts">
          <p className="stat-label">Completed attempts</p>
          <p className="stat-value">{formatCount(period.completed)}</p>
          <p className="stat-foot">
            {formatCount(period.pending)} pending {period.pending === 1 ? "attempt" : "attempts"}, not counted in rates
          </p>
        </section>
        <section className="card stat-card" aria-label="Affected payments">
          <p className="stat-label">Affected payments</p>
          <p className="stat-value">{formatCount(data.recovery.affected_count)}</p>
          <p className="stat-foot">
            <Money cents={data.recovery.affected_cents} /> payment value · {periodFoot}
          </p>
        </section>
      </div>

      <section className="card chart-card" aria-labelledby="trend-heading">
        <div className="section-head">
          <h2 id="trend-heading" className="section-title">
            Daily success rate
          </h2>
          <p className="muted section-aside">
            Dashed line: baseline {formatBps(baseline.success_rate_bps)} ({data.baseline_period.range_label})
          </p>
        </div>
        {period.completed === 0 ? (
          <EmptyState
            title="No completed attempts in this period"
            body={period.pending > 0 ? `${formatCount(period.pending)} pending attempts are still waiting for a result, so no success rate is shown.` : "No success rate is shown for a period without completed attempts."}
          />
        ) : (
          <>
            <RateChart
              title={`Daily completed-attempt success rate, ${data.period.range_label}`}
              baseline={baseline.success_rate_bps}
              formatValue={formatBps}
              points={data.trend.map((p) => ({
                label: formatDateShort(p.day),
                value: p.success_rate_bps,
                lowVolume: p.low_volume,
                detail: `${p.succeeded} succeeded, ${p.failed} failed, ${p.pending} pending${p.partial ? " (today, so far)" : ""}`,
              }))}
            />
            <ul className="chart-legend">
              <li>
                <span className="legend-mark legend-line" aria-hidden="true" /> Success rate
              </li>
              <li>
                <span className="legend-mark legend-baseline" aria-hidden="true" /> Baseline
              </li>
              <li>
                <span className="legend-mark legend-low" aria-hidden="true" /> Low volume: fewer than {data.rules.low_volume_day_completed} completed attempts
              </li>
              <li>Gaps are days with no completed attempts.</li>
            </ul>
          </>
        )}
      </section>

      <section className="card" aria-labelledby="channels-heading">
        <div className="section-head">
          <h2 id="channels-heading" className="section-title">
            Performance by channel
          </h2>
          {data.channel ? (
            <button type="button" className="btn btn-sm" onClick={() => query.set({ channel: null })}>
              Show all channels
            </button>
          ) : (
            <p className="muted section-aside">Select a channel to focus the page on it.</p>
          )}
        </div>
        <ChannelTable channels={data.channels} selected={data.channel} onSelect={(ch) => query.set({ channel: ch === data.channel ? null : ch })} />
      </section>

      <div className="health-grid">
        <section className="card" aria-labelledby="signals-heading">
          <h2 id="signals-heading" className="section-title">
            Recorded failure signals
          </h2>
          <p className="muted health-note">Codes recorded on failed attempts. They describe what was recorded, not a confirmed root cause.</p>
          <SignalTable signals={data.failure_signals} failed={period.failed} scope={scope} />
        </section>

        <section className="card" aria-labelledby="recovery-heading">
          <h2 id="recovery-heading" className="section-title">
            Recovery by payment
          </h2>
          <p className="muted health-note">Payments created in this period that had at least one failed attempt, counted once each at the payment amount.</p>
          <dl className="bucket-list">
            <RecoveryRow label="Affected payments" count={data.recovery.affected_count} cents={data.recovery.affected_cents} />
            <RecoveryRow label="Recovered by a later attempt" count={data.recovery.recovered_count} cents={data.recovery.recovered_cents} />
            <RecoveryRow
              label={`Recovered within ${data.rules.quick_recovery_minutes} minutes of the first attempt`}
              count={data.recovery.recovered_within_hour_count}
              cents={data.recovery.recovered_within_hour_cents}
              nested
            />
            <RecoveryRow label="Unresolved" count={data.recovery.unresolved_count} cents={data.recovery.unresolved_cents} />
            {data.recovery.in_progress_count > 0 ? (
              <RecoveryRow label="Retry in progress" count={data.recovery.in_progress_count} cents={data.recovery.in_progress_cents} />
            ) : null}
          </dl>
        </section>
      </div>

      <section aria-labelledby="unresolved-heading">
        <div className="section-head">
          <h2 id="unresolved-heading" className="section-title">
            Payments that still need attention
          </h2>
          {data.recovery.unresolved_count > 0 ? (
            <Link to={unresolvedHref(scope)} className="section-aside">
              Review all {formatCount(data.recovery.unresolved_count)} in Payments
            </Link>
          ) : null}
        </div>
        <UnresolvedTable items={data.unresolved_payments} total={data.recovery.unresolved_count} />
      </section>

      <Definitions data={data} />
    </div>
  );
}

function AttentionSummary({ data, scope }: { data: PaymentHealth; scope: HealthScope }) {
  const { attention, rules } = data;
  const drop = formatBpsChange(rules.degraded_drop_bps).replace(/^\+/, "");
  const labelOf = (code: string) => data.channels.find((c) => c.channel === code)?.channel_label ?? code;
  const insufficient = attention.insufficient_channels.map(labelOf);
  return (
    <section className={`card health-attention health-attention-${attention.state}`} aria-labelledby="attention-heading" aria-live="polite">
      <div className="health-attention-head">
        <StatusBadge status={attention.state} label={attentionBadge(attention.state)} />
        <h2 id="attention-heading" className="section-title">
          {attentionTitle(data)}
        </h2>
      </div>
      {attention.state === "degraded" ? (
        <ul className="health-evidence">
          {attention.degraded_channels.map((c) => (
            <li key={c.channel}>
              <strong>{c.channel_label}</strong>: {formatBps(c.period.success_rate_bps)} success against a {formatBps(c.baseline.success_rate_bps)} baseline (
              {formatBpsChange(c.change_bps)}), {formatCount(c.period.failed)} failed attempts.{" "}
              <Link to={unresolvedHref(scope, c.channel)}>Review unresolved {c.channel_label.toLowerCase()} payments</Link>
            </li>
          ))}
        </ul>
      ) : null}
      {attention.state === "ok" ? <p className="health-attention-body">Every channel with enough volume is within {drop} of its own baseline.</p> : null}
      {attention.state === "insufficient_data" ? (
        <p className="health-attention-body">
          A channel is judged only with at least {rules.min_period_completed} completed attempts in the period and {rules.min_baseline_completed} in its baseline. No conclusion is drawn here.
        </p>
      ) : null}
      {attention.state === "no_data" ? (
        <p className="health-attention-body">
          {data.scope.period.pending > 0 ? `${formatCount(data.scope.period.pending)} attempts are pending; none has completed yet.` : "No attempts were made in this period."}
        </p>
      ) : null}
      {insufficient.length > 0 && attention.state !== "insufficient_data" ? (
        <p className="health-attention-body muted">Not enough completed attempts to judge: {insufficient.join(", ")}.</p>
      ) : null}
    </section>
  );
}

function attentionBadge(state: string): string {
  if (state === "degraded") return "Degraded";
  if (state === "ok") return "No significant degradation";
  if (state === "insufficient_data") return "Not enough data";
  return "No completed attempts";
}

function attentionTitle(data: PaymentHealth): string {
  const { attention } = data;
  if (attention.state === "degraded") {
    const names = attention.degraded_channels.map((c) => c.channel_label);
    return `${names.join(" and ")} ${names.length === 1 ? "is" : "are"} below baseline`;
  }
  if (attention.state === "ok") return "No significant degradation detected";
  if (attention.state === "insufficient_data") return "Not enough completed attempts to judge";
  return "No completed attempts in this period";
}

function ChannelTable({ channels, selected, onSelect }: { channels: ChannelHealth[]; selected: string | null; onSelect: (channel: string) => void }) {
  if (channels.length === 0) return <EmptyState title="No attempts on this channel" body="Nothing was attempted on the selected channel in this period or its baseline." />;
  const columns: Column<ChannelHealth>[] = [
    {
      key: "channel",
      header: "Channel",
      className: "primary",
      render: (c) => (
        <button
          type="button"
          className="link-button"
          aria-pressed={selected === c.channel}
          onClick={(e) => {
            e.stopPropagation();
            onSelect(c.channel);
          }}
        >
          {c.channel_label}
        </button>
      ),
    },
    { key: "rate", header: "Success rate", align: "right", render: (c) => formatBps(c.period.success_rate_bps) },
    { key: "baseline", header: "Baseline", align: "right", render: (c) => formatBps(c.baseline.success_rate_bps) },
    { key: "change", header: "Change", align: "right", render: (c) => formatBpsChange(c.change_bps) },
    { key: "failed", header: "Failed", align: "right", render: (c) => formatCount(c.period.failed) },
    { key: "completed", header: "Completed", align: "right", render: (c) => formatCount(c.period.completed) },
    { key: "pending", header: "Pending", align: "right", render: (c) => formatCount(c.period.pending) },
    { key: "verdict", header: "Assessment", render: (c) => <StatusBadge status={c.verdict} label={c.verdict_label} /> },
  ];
  return <DataTable caption="Performance by channel" columns={columns} rows={channels} rowKey={(c) => c.channel} onRowClick={(c) => onSelect(c.channel)} />;
}

function SignalTable({ signals, failed, scope }: { signals: FailureSignal[]; failed: number; scope: HealthScope }) {
  if (signals.length === 0) return <EmptyState title="No failed attempts" body="No failure signals were recorded in this period." />;
  const columns: Column<FailureSignal>[] = [
    {
      key: "signal",
      header: "Recorded signal",
      className: "primary",
      render: (s) => (
        <Link to={attemptsHref(scope, s.code)}>{s.label}</Link>
      ),
    },
    { key: "count", header: "Failed attempts", align: "right", render: (s) => formatCount(s.count) },
    { key: "share", header: "Share of failed", align: "right", render: (s) => formatBps(Math.floor((s.count * 20000 + failed) / (failed * 2))) },
  ];
  return <DataTable caption="Recorded failure signals" columns={columns} rows={signals} rowKey={(s) => s.code} />;
}

function RecoveryRow({ label, count, cents, nested = false }: { label: string; count: number; cents: number; nested?: boolean }) {
  return (
    <div className={nested ? "bucket-row bucket-row-nested" : "bucket-row"}>
      <dt>
        {label} · {formatCount(count)}
      </dt>
      <dd className="money">
        <Money cents={cents} />
      </dd>
    </div>
  );
}

function UnresolvedTable({ items, total }: { items: UnresolvedPayment[]; total: number }) {
  const navigate = useNavigate();
  if (items.length === 0) return <EmptyState title="No unresolved payments" body="Every payment with a failed attempt in this period has since succeeded or is still being retried." />;
  const columns: Column<UnresolvedPayment>[] = [
    {
      key: "created_at",
      header: "Created",
      render: (p) => (
        <Link to={`/payments/${p.id}`} className="row-link" onClick={(e) => e.stopPropagation()}>
          <Timestamp iso={p.created_at} />
        </Link>
      ),
    },
    { key: "order", header: "Order", className: "secondary", render: (p) => <span className="mono">{p.order_reference}</span> },
    { key: "customer", header: "Customer", className: "primary", render: (p) => (p.customer ? p.customer.full_name : <span className="muted">Guest</span>) },
    { key: "channel", header: "Channel", render: (p) => p.channel_label },
    { key: "attempts", header: "Failed attempts", align: "right", render: (p) => formatCount(p.failed_attempts) },
    { key: "signal", header: "Last recorded signal", render: (p) => p.last_failure_label },
    { key: "amount", header: "Amount", align: "right", render: (p) => <Money cents={p.amount_cents} /> },
  ];
  return (
    <>
      <DataTable caption="Unresolved payments" columns={columns} rows={items} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/payments/${p.id}`)} />
      {total > items.length ? <p className="muted health-note">Showing the newest {items.length} of {formatCount(total)}.</p> : null}
    </>
  );
}

function Definitions({ data }: { data: PaymentHealth }) {
  const { rules } = data;
  const drop = formatBpsChange(rules.degraded_drop_bps).replace(/^\+/, "");
  return (
    <details className="card health-definitions">
      <summary className="section-title">How these figures are defined</summary>
      <dl>
        <dt>Success rate</dt>
        <dd>Succeeded attempts divided by completed attempts (succeeded plus failed), for attempts made in the period. Pending attempts are shown but left out of the rate.</dd>
        <dt>Baseline</dt>
        <dd>The same channel's success rate over the {rules.baseline_days} days before the selected period ({data.baseline_period.range_label}).</dd>
        <dt>Degraded</dt>
        <dd>
          A channel whose success rate is {drop} or more below its own baseline, judged only when the period has at least {rules.min_period_completed} completed attempts and the baseline at least{" "}
          {rules.min_baseline_completed}. Below those volumes the page says there is not enough data. The rule is fixed; no statistical model is used.
        </dd>
        <dt>Low-volume day</dt>
        <dd>A day with fewer than {rules.low_volume_day_completed} completed attempts. Days with none are left as gaps in the chart.</dd>
        <dt>Affected payment</dt>
        <dd>A payment created in the period with at least one failed attempt. Its value is the payment amount, counted once however many attempts it took.</dd>
        <dt>Recovered</dt>
        <dd>An affected payment that a later attempt completed successfully, at any time up to now. Recovered within {rules.quick_recovery_minutes} minutes means the successful attempt finished within that time of the first attempt.</dd>
        <dt>Unresolved</dt>
        <dd>An affected payment with no successful attempt and no attempt still pending; these are the payments with status Failed. A payment whose retry is still pending is counted as a retry in progress.</dd>
        <dt>Recorded failure signal</dt>
        <dd>The failure code recorded on a failed attempt. It describes what was recorded, not a confirmed root cause.</dd>
        <dt>Periods</dt>
        <dd>Attempt figures count attempts made in the period. Recovery counts payments created in the period and follows their later attempts, so a retry just after the period end still counts.</dd>
      </dl>
    </details>
  );
}
