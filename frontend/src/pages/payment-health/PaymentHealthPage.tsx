import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { ChannelHealth, FailureSignal, PaymentHealth, TrendPoint } from "../../api/payment-health-types";
import type { PaymentListItem } from "../../api/payments-types";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { FilterBar, FilterSelect } from "../../components/FilterBar";
import { LineChart } from "../../components/LineChart";
import { Money } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { formatCount, formatDateShort, formatPercentBp, formatPointsBp } from "../../lib/format";
import { useQueryState } from "../../lib/query";
import { useCurrentSession } from "../../session/SessionProvider";
import { PeriodFilter, periodParams } from "../payments/PeriodFilter";
import { attemptsHref, unresolvedPaymentsHref, type HealthScope } from "./links";

export function PaymentHealthPage() {
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const period = periodParams(query);
  const channel = query.get("channel");
  const health = useApi<PaymentHealth>(`/api/payment-health${queryString({ ...period, channel: channel || undefined })}`);
  const data = health.data;
  const scope: HealthScope = { period, channel };

  return (
    <>
      <PageHeader
        title="Payment Health"
        subtitle="Completed-attempt success by channel against each channel's own baseline, and recovery per payment. Times are shown in America/Chicago."
        actions={
          meta.data ? (
            <FilterBar>
              <PeriodFilter query={query} presets={meta.data.period_presets} idPrefix="health-period" />
              <FilterSelect id="health-channel" label="Channel" value={channel} options={meta.data.channels} onChange={(v) => query.set({ channel: v })} />
            </FilterBar>
          ) : undefined
        }
      />
      {health.error ? <LoadError error={health.error} onRetry={health.reload} /> : null}
      {!health.error && !data ? <LoadingState rows={8} /> : null}
      {data ? <HealthBody data={data} scope={scope} loading={health.loading} onChannel={(c) => query.set({ channel: c })} /> : null}
    </>
  );
}

function HealthBody({ data, scope, loading, onChannel }: { data: PaymentHealth; scope: HealthScope; loading: boolean; onChannel: (channel: string) => void }) {
  const s = data.summary;
  const scopeLabel = data.channel_label ?? "All channels";
  return (
    <div className={loading ? "overview health overview-loading" : "overview health"} aria-busy={loading || undefined}>
      <p className="toolbar-note">
        <span>
          Showing {data.period.label.toLowerCase()}: {data.period.range_label} · {scopeLabel} · compared with the {data.baseline.days} days before ({data.baseline.range_label})
        </span>
      </p>

      <section className="card" aria-labelledby="health-attention-heading">
        <h2 id="health-attention-heading" className="section-title">
          Attention · {data.attention.state_label}
        </h2>
        <HealthAttention data={data} scope={scope} />
      </section>

      {data.channels.length > 0 ? (
        <section className="health-section" aria-labelledby="health-channels-heading">
          <div className="section-head">
            <h2 id="health-channels-heading" className="section-title">
              Performance by channel
            </h2>
            <p className="muted section-aside">Select a channel to scope the page to it.</p>
          </div>
          <ChannelTable data={data} onChannel={onChannel} />
        </section>
      ) : null}

      {s.completed === 0 ? (
        <EmptyState
          title={`No completed attempts · ${scopeLabel}`}
          body={
            s.pending > 0
              ? `${formatCount(s.pending)} ${s.pending === 1 ? "attempt is" : "attempts are"} still pending and not counted in a success rate. There is no rate to show for this period.`
              : "There were no succeeded or failed attempts in this period, so there is no success rate to show."
          }
          action={s.pending > 0 ? <Link to={attemptsHref(scope, { outcome: "pending" })}>View pending attempts</Link> : undefined}
        />
      ) : (
        <ScopedHealth data={data} scope={scope} />
      )}

      <Definitions data={data} />
    </div>
  );
}

function ScopedHealth({ data, scope }: { data: PaymentHealth; scope: HealthScope }) {
  const s = data.summary;
  const r = data.recovery;
  const baselineUsable = s.baseline.success_rate_bp !== null && s.baseline.completed >= data.rules.min_baseline_completed;
  return (
    <>
      <div className="cards cards-4">
        <section className="card stat-card" aria-label="Success rate">
          <p className="stat-label">Success rate · completed attempts</p>
          <p className="stat-value">{formatPercentBp(s.success_rate_bp)}</p>
          <p className="stat-foot">
            {s.baseline.success_rate_bp === null
              ? "No baseline: no completed attempts before this period"
              : `Baseline ${formatPercentBp(s.baseline.success_rate_bp)} · ${formatPointsBp(s.change_bp)}`}
          </p>
          <p className="stat-foot">
            <Link to={attemptsHref(scope)}>{formatCount(s.completed)} completed attempts</Link>
          </p>
        </section>
        <section className="card stat-card" aria-label="Failed attempts">
          <p className="stat-label">Failed attempts</p>
          <p className="stat-value num">{formatCount(s.failed)}</p>
          <p className="stat-foot">Baseline {formatCount(s.baseline.failed)} over {data.baseline.days} days</p>
          {s.failed > 0 ? (
            <p className="stat-foot">
              <Link to={attemptsHref(scope, { outcome: "failed" })}>Review failed attempts</Link>
            </p>
          ) : null}
        </section>
        <section className="card stat-card" aria-label="Pending attempts">
          <p className="stat-label">Pending attempts</p>
          <p className="stat-value num">{formatCount(s.pending)}</p>
          <p className="stat-foot">Not counted in the success rate until they complete</p>
          {s.pending > 0 ? (
            <p className="stat-foot">
              <Link to={attemptsHref(scope, { outcome: "pending" })}>View pending attempts</Link>
            </p>
          ) : null}
        </section>
        <section className="card stat-card" aria-label="Affected payments">
          <p className="stat-label">Affected payments</p>
          <p className="stat-value num">{formatCount(r.affected_payments)}</p>
          <p className="stat-foot">
            {formatCount(r.recovered_payments)} recovered · {formatCount(r.unresolved_payments)} unresolved
          </p>
        </section>
      </div>

      <section className="card chart-card" aria-labelledby="health-trend-heading">
        <div className="section-head">
          <h2 id="health-trend-heading" className="section-title">
            Success rate by day
          </h2>
          <p className="muted section-aside">
            {data.channel_label ?? "All channels"} · {data.period.range_label}
          </p>
        </div>
        <LineChart
          title={`Completed-attempt success rate by day, ${data.channel_label ?? "all channels"}, ${data.period.range_label}`}
          points={data.trend.map(trendPoint)}
          reference={baselineUsable && s.baseline.success_rate_bp !== null ? { value: s.baseline.success_rate_bp, label: `Baseline ${formatPercentBp(s.baseline.success_rate_bp)}` } : null}
          formatTick={(bp) => `${bp / 100}%`}
          max={10000}
          step={1000}
          seriesLabel="Daily success rate"
          lowVolumeLabel={`Low volume: fewer than ${data.rules.low_volume_day_completed} completed attempts`}
          gapLabel="Gap: no completed attempts that day"
        />
        {!baselineUsable ? (
          <p className="muted chart-note">
            Baseline not drawn: {formatCount(s.baseline.completed)} completed attempts in {data.baseline.range_label}, fewer than the {formatCount(data.rules.min_baseline_completed)} needed for a comparison.
          </p>
        ) : null}
      </section>

      <div className="overview-grid">
        <section className="health-section" aria-labelledby="health-signals-heading">
          <div className="section-head">
            <h2 id="health-signals-heading" className="section-title">
              Recorded failure signals
            </h2>
          </div>
          <p className="muted section-note">
            The codes recorded on failed attempts. They are signals for investigation, not confirmed root causes. Counts add up to the {formatCount(s.failed)} failed attempts.
          </p>
          <FailureSignals signals={data.failure_signals} scope={scope} />
        </section>
        <section className="card" aria-labelledby="health-recovery-heading">
          <h2 id="health-recovery-heading" className="section-title">
            Recovery by payment
          </h2>
          <Recovery data={data} scope={scope} />
        </section>
      </div>

      <section className="health-section" aria-labelledby="health-unresolved-heading">
        <div className="section-head">
          <h2 id="health-unresolved-heading" className="section-title">
            Unresolved payments
          </h2>
          {r.unresolved_payments > 0 ? (
            <Link to={unresolvedPaymentsHref(scope)} className="section-aside">
              Review all {formatCount(r.unresolved_payments)} in Payments
            </Link>
          ) : null}
        </div>
        <UnresolvedPayments items={data.unresolved_payments} total={r.unresolved_payments} />
      </section>
    </>
  );
}

function trendPoint(p: TrendPoint) {
  const counts = `${formatCount(p.succeeded)} succeeded, ${formatCount(p.failed)} failed, ${formatCount(p.pending)} pending`;
  return {
    label: formatDateShort(p.day),
    value: p.success_rate_bp,
    lowVolume: p.low_volume,
    detail: p.success_rate_bp === null ? `No completed attempts · ${counts}` : `${formatPercentBp(p.success_rate_bp)} · ${counts}${p.low_volume ? " · low volume" : ""}`,
  };
}

function insufficientDetail(c: ChannelHealth, data: PaymentHealth): string {
  const { min_period_completed: minPeriod, min_baseline_completed: minBaseline } = data.rules;
  const short: string[] = [];
  if (c.completed < minPeriod) short.push(`${formatCount(c.completed)} of ${formatCount(minPeriod)} completed attempts in the period`);
  if (c.baseline_completed < minBaseline) short.push(`${formatCount(c.baseline_completed)} of ${formatCount(minBaseline)} in the baseline`);
  return short.join("; ");
}

function HealthAttention({ data, scope }: { data: PaymentHealth; scope: HealthScope }) {
  const drop = formatPointsBp(data.rules.degraded_drop_bp, { sign: false });
  const insufficient = data.channels.filter((c) => c.assessment === "insufficient_volume");
  const items: { key: string; kind: string; title: ReactNode; detail: ReactNode }[] = [];
  for (const d of data.attention.degraded_channels) {
    items.push({
      key: `degraded-${d.channel}`,
      kind: "degraded",
      title: `${d.channel_label} is degraded`,
      detail: (
        <>
          {formatPercentBp(d.success_rate_bp)} success against a {formatPercentBp(d.baseline_rate_bp)} baseline ({formatPointsBp(d.change_bp)}) · {formatCount(d.failed)} failed attempts.{" "}
          <Link to={unresolvedPaymentsHref(scope, d.channel)}>Review unresolved {d.channel_label.toLowerCase()} payments</Link>
          {" · "}
          <Link to={attemptsHref(scope, { outcome: "failed" }, d.channel)}>View failed attempts</Link>
        </>
      ),
    });
  }
  if (data.attention.state === "healthy") {
    items.push({
      key: "healthy",
      kind: "healthy",
      title: "No significant degradation detected",
      detail: `Every channel with enough volume is within ${drop} of its own baseline.`,
    });
  }
  if (data.attention.state === "no_completed_attempts") {
    items.push({ key: "none", kind: "neutral", title: "No completed attempts in this period", detail: "There is nothing to compare against a baseline." });
  }
  if (insufficient.length > 0) {
    items.push({
      key: "insufficient",
      kind: "neutral",
      title: data.attention.state === "insufficient_volume" ? "Not enough volume to evaluate any channel" : "Not enough volume to evaluate",
      detail: (
        <>
          No conclusion is drawn for{" "}
          {insufficient.map((c, i) => (
            <span key={c.channel}>
              {i > 0 ? "; " : null}
              {c.channel_label} ({insufficientDetail(c, data)})
            </span>
          ))}
          .
        </>
      ),
    });
  }
  return (
    <ul className="attention-list">
      {items.map((item) => (
        <li key={item.key} className={`attention-item attention-${item.kind}`}>
          <span className="attention-dot" aria-hidden="true" />
          <div className="attention-body">
            <p className="attention-title">{item.title}</p>
            <p className="attention-detail muted">{item.detail}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function ChannelTable({ data, onChannel }: { data: PaymentHealth; onChannel: (channel: string) => void }) {
  const columns: Column<ChannelHealth>[] = [
    {
      key: "channel",
      header: "Channel",
      className: "primary",
      render: (c) => (
        <button type="button" className="link-button" aria-pressed={data.channel === c.channel} onClick={() => onChannel(c.channel)}>
          {c.channel_label}
        </button>
      ),
    },
    { key: "rate", header: "Success rate", align: "right", render: (c) => formatPercentBp(c.success_rate_bp) },
    { key: "baseline", header: "Baseline", align: "right", render: (c) => formatPercentBp(c.baseline_rate_bp) },
    { key: "change", header: "Change", align: "right", render: (c) => formatPointsBp(c.change_bp) },
    { key: "completed", header: "Completed", align: "right", render: (c) => formatCount(c.completed) },
    { key: "failed", header: "Failed", align: "right", render: (c) => formatCount(c.failed) },
    { key: "pending", header: "Pending", align: "right", render: (c) => formatCount(c.pending) },
    {
      key: "assessment",
      header: "Assessment",
      render: (c) => (
        <>
          <StatusBadge status={c.assessment} label={c.assessment_label} />
          {c.assessment === "insufficient_volume" ? <span className="cell-note muted">{insufficientDetail(c, data)}</span> : null}
        </>
      ),
    },
  ];
  return (
    <>
      <DataTable caption="Performance by channel" columns={columns} rows={data.channels} rowKey={(c) => c.channel} />
      {data.channel ? (
        <p className="section-note">
          <button type="button" className="link-button" onClick={() => onChannel("")}>
            Show all channels
          </button>
        </p>
      ) : null}
    </>
  );
}

function FailureSignals({ signals, scope }: { signals: FailureSignal[]; scope: HealthScope }) {
  if (signals.length === 0) return <EmptyState title="No failed attempts" body="No failure signals were recorded in this period." />;
  const columns: Column<FailureSignal>[] = [
    {
      key: "label",
      header: "Recorded signal",
      className: "primary",
      render: (f) => <Link to={attemptsHref(scope, { outcome: "failed", failure_code: f.failure_code })}>{f.label}</Link>,
    },
    { key: "code", header: "Code", render: (f) => <span className="mono">{f.failure_code}</span> },
    { key: "count", header: "Failed attempts", align: "right", render: (f) => formatCount(f.failed_attempts) },
  ];
  return <DataTable caption="Recorded failure signals" columns={columns} rows={signals} rowKey={(f) => f.failure_code} />;
}

function Recovery({ data, scope }: { data: PaymentHealth; scope: HealthScope }) {
  const r = data.recovery;
  const session = useCurrentSession();
  const minutes = data.rules.quick_recovery_seconds / 60;
  const quickWindow = minutes === 60 ? "1 hour" : `${minutes} minutes`;
  const row = (label: string, count: number, cents: number, extra?: ReactNode) => (
    <div className="bucket-row">
      <dt>
        {label}
        {extra ? <span className="cell-note muted">{extra}</span> : null}
      </dt>
      <dd className="money">
        {formatCount(count)} · <Money cents={cents} />
      </dd>
    </div>
  );
  return (
    <>
      <p className="muted section-note">
        Payments created in the period with at least one failed attempt, each counted once with its payment amount, as of <Timestamp iso={session.as_of} mode="full" />.
      </p>
      <dl className="bucket-list">
        {row("Affected payments", r.affected_payments, r.affected_value_cents)}
        {row("Recovered on retry", r.recovered_payments, r.recovered_value_cents, `${formatCount(r.recovered_within_hour_payments)} within ${quickWindow} of the first attempt`)}
        {row("Retry in progress", r.in_progress_payments, r.in_progress_value_cents)}
        {row("Unresolved", r.unresolved_payments, r.unresolved_value_cents)}
      </dl>
      {r.unresolved_payments > 0 ? (
        <p className="stat-foot">
          <Link to={unresolvedPaymentsHref(scope)}>Review unresolved payments</Link>
        </p>
      ) : null}
    </>
  );
}

function UnresolvedPayments({ items, total }: { items: PaymentListItem[]; total: number }) {
  const navigate = useNavigate();
  if (items.length === 0) return <EmptyState title="No unresolved payments" body="Every affected payment in this period has recovered or is still being retried." />;
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
    { key: "order", header: "Order", className: "secondary", render: (p) => <span className="mono">{p.order_reference}</span> },
    { key: "customer", header: "Customer", className: "primary", render: (p) => (p.customer ? p.customer.full_name : <span className="muted">Guest</span>) },
    { key: "channel", header: "Channel", render: (p) => p.channel_label },
    { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} label={p.status_label} /> },
    { key: "amount", header: "Amount", align: "right", render: (p) => <Money cents={p.amount_cents} /> },
  ];
  return (
    <>
      <DataTable caption="Unresolved payments" columns={columns} rows={items} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/payments/${p.id}`)} />
      {total > items.length ? <p className="muted section-note">Showing the {items.length} most recent of {formatCount(total)}.</p> : null}
    </>
  );
}

function Definitions({ data }: { data: PaymentHealth }) {
  const rules = data.rules;
  const minutes = rules.quick_recovery_seconds / 60;
  const items: [string, string][] = [
    ["Success rate", "Succeeded ÷ (succeeded + failed) for attempts created in the period. Pending attempts are shown but not counted. This is attempt success, not purchase conversion."],
    ["Baseline", `The same channel (or all channels) over the ${rules.baseline_days} days before the period: ${data.baseline.range_label}.`],
    [
      "Degraded",
      `A success rate at least ${formatPointsBp(rules.degraded_drop_bp, { sign: false })} below the channel's baseline, compared on unrounded basis points. A channel is evaluated only with at least ${formatCount(rules.min_period_completed)} completed attempts in the period and ${formatCount(rules.min_baseline_completed)} in the baseline; otherwise no conclusion is drawn.`,
    ],
    ["Low-volume day", `A day with fewer than ${formatCount(rules.low_volume_day_completed)} completed attempts. A day with none is a gap in the chart.`],
    ["Affected payment", "A payment created in the period with at least one failed attempt, however many attempts it took."],
    ["Recovered", `An affected payment with a later successful attempt. "Within ${minutes === 60 ? "1 hour" : `${minutes} minutes`}" measures from the first attempt to the successful one.`],
    ["Retry in progress", "An affected payment whose latest attempt is still pending."],
    ["Unresolved", "An affected payment with no successful attempt whose latest attempt failed. These are the failed payments in the Payments list."],
    ["Recorded failure signal", "The code recorded on a failed attempt. A signal for investigation, not a confirmed root cause."],
  ];
  return (
    <details className="card definitions">
      <summary className="section-title">How these figures are defined</summary>
      <dl className="definition-list">
        {items.map(([term, text]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd>{text}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

