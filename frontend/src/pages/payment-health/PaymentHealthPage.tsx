import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { ChannelHealth, ChannelStatus, FailureSignal, PaymentHealth, UnresolvedPayment } from "../../api/payment-health-types";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { FilterBar, FilterSelect } from "../../components/FilterBar";
import { InfoTip } from "../../components/InfoTip";
import { LineChart, type LineChartPoint } from "../../components/LineChart";
import { Money } from "../../components/Money";
import { StatusBadge, toneFor } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { formatCount, formatDate, formatDateShort, formatPointsBp, formatRateBp, formatTimestampFull } from "../../lib/format";
import { failedAttemptsHref, scopeFromPeriod, unresolvedPaymentsHref, type HealthScope } from "../../lib/healthScope";
import { useQueryState, type QueryState } from "../../lib/query";
import { PeriodFilter, periodParams } from "../payments/PeriodFilter";

/* Definitions quoted on the page. Every other sentence reads its thresholds from data.rule. */
const SUCCESS_RATE_DEFINITION = "Percentage of completed payment attempts that succeeded. Pending attempts are excluded.";
const AFFECTED_DEFINITION = "Payments in this period with at least one failed attempt, counted once per payment however many attempts it took.";
const SIGNAL_DEFINITION = "Reason recorded on the failed attempt. It doesn't necessarily establish the underlying cause.";
const RECOVERED_DEFINITION =
  "An affected payment that later succeeded. Within 1 hour means the successful attempt completed no more than an hour after the payment's first attempt was created.";

const NO_FAILED_ATTEMPTS = "No failed attempts in the selected period";
const NO_COMPLETED_ATTEMPTS = "No completed attempts";

export function PaymentHealthPage() {
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const health = useApi<PaymentHealth>(`/api/payment-health${queryString({ ...periodParams(query), channel: query.get("channel") || undefined })}`);
  const data = health.data;

  return (
    <>
      <PageHeader
        title="Payment Health"
        subtitle="Understand payment performance and investigate degradation."
        actions={
          meta.data ? (
            <FilterBar>
              <PeriodFilter query={query} presets={meta.data.period_presets} idPrefix="health-period" />
              <FilterSelect id="health-channel" label="Channel" allLabel="All channels" value={query.get("channel")} options={meta.data.channels} onChange={(v) => query.set({ channel: v })} />
            </FilterBar>
          ) : undefined
        }
      />
      {health.error ? <LoadError error={health.error} onRetry={health.reload} /> : null}
      {!health.error && !data ? <LoadingState rows={8} /> : null}
      {data ? <HealthBody data={data} query={query} loading={health.loading} /> : null}
    </>
  );
}

function pendingLine(pending: number): string {
  const one = pending === 1;
  return `${formatCount(pending)} attempt${one ? "" : "s"} ${one ? "is" : "are"} still pending; figures may change.`;
}

/** Gridline labels read better without the decimal: 7500 -> "75%". */
function wholeTick(bp: number): string {
  return formatRateBp(bp).replace(/\.0%$/, "%");
}

/** The current page with one channel swapped in, so a channel link keeps the period. */
function channelHref(query: QueryState, channel: string | null): string {
  const params = new URLSearchParams(query.search);
  if (channel) params.set("channel", channel);
  else params.delete("channel");
  params.delete("page");
  const search = params.toString();
  return `/payment-health${search ? `?${search}` : ""}`;
}

function HealthBody({ data, query, loading }: { data: PaymentHealth; query: QueryState; loading: boolean }) {
  const scope = scopeFromPeriod(data.period, data.channel);
  const { period } = data.scope;
  const noCompleted = period.completed === 0;
  const noFailed = !noCompleted && period.failed === 0;

  return (
    <div className={loading ? "health health-loading" : "health"} aria-busy={loading || undefined}>
      <p className="health-scope muted">
        {data.channel_label} · {data.period.range_label} · As of {formatTimestampFull(data.as_of)}
      </p>
      {period.pending > 0 ? (
        <p className="health-pending" role="status">
          {pendingLine(period.pending)}
        </p>
      ) : null}

      {noCompleted ? (
        <EmptyState
          title="No completed attempts in this period"
          body={
            period.pending > 0
              ? `${formatCount(period.pending)} attempt${period.pending === 1 ? " is" : "s are"} still pending in ${data.channel_label.toLowerCase()} for ${data.period.range_label}; a rate needs at least one completed attempt.`
              : `No payment attempts completed in ${data.channel_label.toLowerCase()} for ${data.period.range_label}. Try a wider period or another channel.`
          }
        />
      ) : (
        <>
          <AttentionCard data={data} scope={scope} />
          <KpiRow data={data} />
          <TrendCard data={data} />
        </>
      )}

      <ChannelTable data={data} query={query} />

      {noFailed ? (
        <section className="card health-none" aria-label="Failed attempts">
          <p className="health-none-text">{NO_FAILED_ATTEMPTS}</p>
        </section>
      ) : null}

      {!noCompleted && !noFailed ? (
        <>
          <SignalsCard data={data} scope={scope} />
          <div className="health-grid">
            <RecoveryCard data={data} />
            <ValueCard data={data} />
          </div>
          <UnresolvedCard data={data} scope={scope} />
        </>
      ) : null}
    </div>
  );
}

/* ----------------------------------------------------------------------- attention */

function AttentionCard({ data, scope }: { data: PaymentHealth; scope: HealthScope }) {
  const { attention } = data;
  const tone = toneFor(attention.status);
  // On the all-channels view the button lands on the first degraded channel's failures, not every channel's.
  const reviewScope: HealthScope = data.channel === null && attention.degraded_channels.length > 0 ? { ...scope, channel: attention.degraded_channels[0] ?? null } : scope;
  return (
    <section className={`card health-attention health-attention-${tone}`} role="status" aria-labelledby="health-attention-heading">
      <div className="health-attention-body">
        <div className="health-attention-head">
          <h2 id="health-attention-heading" className="section-title">
            {attention.headline}
          </h2>
          <StatusBadge status={data.scope.status} label={data.scope.status_label} />
        </div>
        <p className="health-attention-detail">{attention.detail}</p>
      </div>
      {attention.status === "degraded" ? (
        <div className="health-attention-action">
          <Link className="btn btn-primary" to={unresolvedPaymentsHref(reviewScope)}>
            Review unresolved payments
          </Link>
        </div>
      ) : null}
    </section>
  );
}

/* ----------------------------------------------------------------------- KPIs */

function successRateFoot(data: PaymentHealth): string[] {
  const { status, period, baseline } = data.scope;
  const { rule } = data;
  if (status === "no_baseline") return ["No baseline yet"];
  if (status === "insufficient_volume") {
    if (period.completed < rule.min_period_completed) return [`${formatCount(period.completed)} completed attempts; ${formatCount(rule.min_period_completed)} needed to evaluate`];
    return [`${formatCount(baseline.completed)} completed baseline attempts; ${formatCount(rule.min_baseline_completed)} needed to evaluate`];
  }
  if (period.success_rate_bp === null || baseline.success_rate_bp === null) return [];
  const history = data.baseline.partial && data.baseline.history_starts ? `, history from ${formatDate(data.baseline.history_starts)}` : "";
  return [`vs ${formatRateBp(baseline.success_rate_bp)} baseline (${formatPointsBp(period.success_rate_bp - baseline.success_rate_bp)})`, `Baseline: ${data.baseline.range_label}${history}`];
}

function KpiCard({ label, level, tip, value, feet }: { label: string; level: "Attempt-level" | "Payment-level"; tip?: { text: string; label: string }; value: ReactNode; feet: ReactNode[] }) {
  return (
    <section className="card stat-card health-kpi" aria-label={label}>
      <span className="health-level">{level}</span>
      {/* The definition sits before the label in the DOM so the card's figures read as one phrase; CSS shows it after. */}
      <p className="stat-label health-kpi-label">
        {tip ? <InfoTip text={tip.text} label={tip.label} /> : null}
        <span>{label}</span>
      </p>
      <p className="stat-value">{value}</p>
      {feet.map((foot, i) => (
        <p key={i} className="stat-foot">
          {foot}
        </p>
      ))}
    </section>
  );
}

function KpiRow({ data }: { data: PaymentHealth }) {
  const { period } = data.scope;
  const { recovery } = data;
  const recoveryFoot = `${formatCount(recovery.recovered)} recovered · ${formatCount(recovery.unresolved)} unresolved${recovery.attempt_pending > 0 ? ` · ${formatCount(recovery.attempt_pending)} attempt pending` : ""}`;
  return (
    <div className="cards cards-4 health-kpis">
      <KpiCard
        label="Attempt success rate"
        level="Attempt-level"
        tip={{ text: SUCCESS_RATE_DEFINITION, label: "What is attempt success rate?" }}
        value={period.success_rate_bp === null ? NO_COMPLETED_ATTEMPTS : formatRateBp(period.success_rate_bp)}
        feet={successRateFoot(data)}
      />
      <KpiCard
        label="Failed attempts"
        level="Attempt-level"
        value={formatCount(period.failed)}
        feet={[period.failed_share_bp === null ? NO_COMPLETED_ATTEMPTS : `${formatRateBp(period.failed_share_bp)} of ${formatCount(period.completed)} completed attempts`]}
      />
      <KpiCard
        label="Affected payments"
        level="Payment-level"
        tip={{ text: AFFECTED_DEFINITION, label: "What is an affected payment?" }}
        value={formatCount(recovery.affected)}
        feet={[recoveryFoot]}
      />
      <KpiCard
        label="Affected payment value"
        level="Payment-level"
        value={<Money cents={recovery.affected_cents} />}
        feet={[
          <>
            <Money cents={recovery.recovered_cents} /> recovered · <Money cents={recovery.unresolved_cents} /> unresolved
          </>,
        ]}
      />
    </div>
  );
}

/* ----------------------------------------------------------------------- trend */

function TrendCard({ data }: { data: PaymentHealth }) {
  const { period } = data.scope;
  const series: LineChartPoint[] = data.trend.points.map((p) => {
    const day = formatDateShort(p.day);
    const rate = p.success_rate_bp === null ? "no completed attempts" : formatRateBp(p.success_rate_bp);
    return { label: day, value: p.success_rate_bp, lowVolume: p.low_volume, tooltip: `${day}: ${rate} · ${formatCount(p.failed)} failed of ${formatCount(p.completed)} completed` };
  });
  const baseline = data.trend.baseline_rate_bp;
  return (
    <section className="card chart-card" aria-labelledby="health-trend-heading">
      <div className="section-head">
        <h2 id="health-trend-heading" className="section-title">
          Payment performance over time
        </h2>
        <p className="muted section-aside">
          {period.success_rate_bp === null ? NO_COMPLETED_ATTEMPTS : `${formatRateBp(period.success_rate_bp)} of completed attempts succeeded`} · {data.period.range_label}
        </p>
      </div>
      <LineChart
        title={`Daily completed-attempt success rate, ${data.channel_label}, ${data.period.range_label}`}
        series={series}
        baseline={baseline}
        baselineLabel={baseline === null ? undefined : `Baseline ${formatRateBp(baseline)}`}
        formatTick={wholeTick}
        lowVolumeLegend={`Fewer than ${formatCount(data.rule.low_volume_day_completed)} completed attempts`}
      />
    </section>
  );
}

/* ----------------------------------------------------------------------- channels */

function ChannelTable({ data, query }: { data: PaymentHealth; query: QueryState }) {
  const selected = data.channel;
  const columns: Column<ChannelHealth>[] = [
    {
      key: "channel",
      header: "Channel",
      className: "primary",
      render: (c) => (
        <Link
          to={channelHref(query, c.channel)}
          className={c.channel === selected ? "row-link health-channel-link health-channel-selected" : "row-link health-channel-link"}
          aria-current={c.channel === selected ? "true" : undefined}
          onClick={(e) => e.stopPropagation()}
        >
          {c.channel_label}
        </Link>
      ),
    },
    { key: "rate", header: "Success rate (period)", align: "right", render: (c) => (c.period.success_rate_bp === null ? <span className="muted">—</span> : formatRateBp(c.period.success_rate_bp)) },
    { key: "baseline", header: "Baseline", align: "right", render: (c) => (c.baseline.success_rate_bp === null ? <span className="muted">—</span> : formatRateBp(c.baseline.success_rate_bp)) },
    { key: "completed", header: "Completed attempts", align: "right", render: (c) => formatCount(c.period.completed) },
    { key: "status", header: "Status", render: (c) => <StatusBadge status={c.status} label={c.status_label} /> },
  ];
  return (
    <section className="card health-channels" aria-labelledby="health-channels-heading">
      <div className="section-head">
        <h2 id="health-channels-heading" className="section-title">
          Performance by channel
        </h2>
        <p className="muted section-aside">Each channel is evaluated against its own baseline</p>
      </div>
      <DataTable caption="Performance by channel" columns={columns} rows={data.channels} rowKey={(c) => c.channel ?? "all"} onRowClick={(c) => query.set({ channel: c.channel })} />
    </section>
  );
}

/* ----------------------------------------------------------------------- failure signals */

function SignalsCard({ data, scope }: { data: PaymentHealth; scope: HealthScope }) {
  const { failure_signals: signals } = data;
  const columns: Column<FailureSignal>[] = [
    {
      key: "signal",
      header: "Recorded signal",
      className: "primary",
      render: (s) => (
        <>
          {s.label} <span className="mono muted">{s.failure_code}</span>
        </>
      ),
    },
    { key: "count", header: "Failed attempts", align: "right", render: (s) => formatCount(s.count) },
    { key: "share", header: "Share", align: "right", render: (s) => formatRateBp(s.share_bp) },
    {
      key: "link",
      header: <span className="visually-hidden">Attempts</span>,
      render: (s) => (
        <Link to={failedAttemptsHref(scope, s.failure_code)} className="health-view-link">
          View attempts
        </Link>
      ),
    },
  ];
  return (
    <section className="card health-signals" aria-labelledby="health-signals-heading">
      <div className="section-head">
        <h2 id="health-signals-heading" className="section-title health-title-tip">
          Recorded failure signals <InfoTip text={SIGNAL_DEFINITION} label="What is a recorded failure signal?" />
        </h2>
        <p className="muted section-aside">
          {formatCount(signals.total_failed)} failed attempt{signals.total_failed === 1 ? "" : "s"} in this scope
        </p>
      </div>
      {signals.total_failed === 0 ? (
        <p className="health-none-text">{NO_FAILED_ATTEMPTS}</p>
      ) : (
        <>
          {signals.primary ? (
            <p className="health-primary">
              <strong>Primary recorded signal:</strong> {signals.primary.label} accounts for {formatRateBp(signals.primary.share_bp)} of failed attempts in this scope.
            </p>
          ) : null}
          <DataTable caption="Recorded failure signals" columns={columns} rows={signals.items} rowKey={(s) => s.failure_code} />
        </>
      )}
    </section>
  );
}

/* ----------------------------------------------------------------------- recovery */

function FlowStep({ label, value, detail, tone }: { label: string; value: number; detail?: string; tone?: ChannelStatus | "info" }) {
  return (
    <li className={tone ? `health-flow-step health-flow-${tone}` : "health-flow-step"}>
      <span className="health-flow-label">{label}</span>{" "}
      <span className="health-flow-value num">
        {formatCount(value)}
        {detail ? ` (${detail})` : ""}
      </span>
    </li>
  );
}

function RecoveryCard({ data }: { data: PaymentHealth }) {
  const r = data.recovery;
  const windowLabel = r.affected > 0 && r.recovered_within_window_share_bp !== null ? formatRateBp(r.recovered_within_window_share_bp) : undefined;
  return (
    <section className="card health-recovery" aria-labelledby="health-recovery-heading">
      <h2 id="health-recovery-heading" className="section-title health-title-tip">
        Recovery after a failed attempt <InfoTip text={RECOVERED_DEFINITION} label="What does recovered mean?" />
      </h2>
      <ol className="health-flow">
        <FlowStep label="Affected payments" value={r.affected} />
        <FlowStep label="Recovered within 1 hour" value={r.recovered_within_window} detail={windowLabel} tone="normal" />
        {r.recovered_later > 0 ? <FlowStep label="Recovered after 1 hour" value={r.recovered_later} tone="normal" /> : null}
        {r.attempt_pending > 0 ? <FlowStep label="Attempt pending" value={r.attempt_pending} tone="info" /> : null}
        <FlowStep label="Unresolved" value={r.unresolved} tone="degraded" />
      </ol>
      <p className="stat-foot">Counted once per payment. A payment declined twice and then completed is one affected payment and one recovered payment.</p>
    </section>
  );
}

function ValueCard({ data }: { data: PaymentHealth }) {
  const r = data.recovery;
  return (
    <section className="card health-value" aria-labelledby="health-value-heading">
      <h2 id="health-value-heading" className="section-title">
        Payment value affected
      </h2>
      <dl className="bucket-list">
        <ValueRow label="Affected" cents={r.affected_cents} />
        <ValueRow label="Recovered" cents={r.recovered_cents} />
        <ValueRow label="Unresolved" cents={r.unresolved_cents} />
        {r.attempt_pending > 0 ? <ValueRow label="Attempt pending" cents={r.attempt_pending_cents} /> : null}
      </dl>
      <p className="stat-foot">Payment amount counted once per payment.</p>
    </section>
  );
}

function ValueRow({ label, cents }: { label: string; cents: number }) {
  return (
    <div className="bucket-row">
      <dt>{label}</dt>
      <dd className="money">
        <Money cents={cents} />
      </dd>
    </div>
  );
}

/* ----------------------------------------------------------------------- unresolved payments */

function UnresolvedCard({ data, scope }: { data: PaymentHealth; scope: HealthScope }) {
  const navigate = useNavigate();
  const { unresolved_payments: unresolved } = data;
  const columns: Column<UnresolvedPayment>[] = [
    {
      key: "order",
      header: "Order",
      className: "secondary",
      render: (p) => (
        <Link to={`/payments/${p.id}`} className="row-link mono" onClick={(e) => e.stopPropagation()}>
          {p.order_reference}
        </Link>
      ),
    },
    { key: "customer", header: "Customer", className: "primary", render: (p) => (p.customer ? p.customer.full_name : <span className="muted">Guest</span>) },
    { key: "amount", header: "Amount", align: "right", render: (p) => <Money cents={p.amount_cents} /> },
    { key: "last_attempt", header: "Last attempt", render: (p) => <Timestamp iso={p.last_attempt_at} mode="relative" /> },
    { key: "signal", header: "Last recorded signal", render: (p) => p.last_failure_label ?? <span className="muted">—</span> },
    { key: "attempts", header: "Attempts", align: "right", render: (p) => formatCount(p.attempt_count) },
  ];
  return (
    <section className="card health-unresolved" aria-labelledby="health-unresolved-heading">
      <div className="section-head">
        <h2 id="health-unresolved-heading" className="section-title">
          Payments requiring attention
        </h2>
        <p className="muted section-aside">Unresolved: no attempt has succeeded and none is pending</p>
      </div>
      {unresolved.total === 0 ? (
        <p className="health-none-text">No unresolved payments in this scope.</p>
      ) : (
        <>
          <DataTable caption="Payments requiring attention" columns={columns} rows={unresolved.items} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/payments/${p.id}`)} />
          <p className="health-review-all">
            <Link to={unresolvedPaymentsHref(scope)}>Review all {formatCount(unresolved.total)} unresolved payments</Link>
          </p>
        </>
      )}
    </section>
  );
}
