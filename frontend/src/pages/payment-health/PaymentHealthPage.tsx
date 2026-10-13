import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { ChannelHealth, FailureSignal, HealthThresholds, PaymentHealth, UnresolvedPayment } from "../../api/payment-health-types";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { DescriptionList } from "../../components/DescriptionList";
import { FilterBar, FilterSelect } from "../../components/FilterBar";
import { Money } from "../../components/Money";
import { RateChart } from "../../components/RateChart";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { formatCount, formatDateShort, formatPoints, formatRate } from "../../lib/format";
import { useQueryState } from "../../lib/query";
import { PeriodFilter } from "../payments/PeriodFilter";
import { attemptsDrill, healthScope, paymentsDrill, type HealthScope } from "./links";

export function PaymentHealthPage() {
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const scope = healthScope(query);
  const health = useApi<PaymentHealth>(`/api/payment-health${queryString(scope)}`);
  const data = health.data;

  return (
    <>
      <PageHeader
        title="Payment Health"
        subtitle="Completed-attempt success by channel, compared with each channel's own baseline. Times are shown in America/Chicago."
        actions={
          meta.data ? (
            <FilterBar>
              <PeriodFilter query={query} presets={meta.data.period_presets} idPrefix="health-period" />
              <FilterSelect id="health-channel" label="Channel" value={query.get("channel")} options={meta.data.channels} onChange={(v) => query.set({ channel: v })} />
            </FilterBar>
          ) : undefined
        }
      />
      {health.error ? <LoadError error={health.error} onRetry={health.reload} /> : null}
      {!health.error && !data ? <LoadingState rows={8} /> : null}
      {data ? <HealthBody data={data} scope={scope} loading={health.loading} onScopeChannel={(channel) => query.set({ channel })} /> : null}
    </>
  );
}

function HealthBody({ data, scope, loading, onScopeChannel }: { data: PaymentHealth; scope: HealthScope; loading: boolean; onScopeChannel: (channel: string | null) => void }) {
  const period = data.summary.period;
  const periodFoot = `${data.channel_label} · ${data.period.range_label}`;
  return (
    <div className={loading ? "overview overview-loading" : "overview"} aria-busy={loading || undefined}>
      <AttentionSummary data={data} scope={scope} />

      {period.completed === 0 && period.pending === 0 ? (
        <EmptyState title="No payment attempts in this period" body="There is nothing to rate. Try a wider period or another channel." />
      ) : (
        <>
          <div className="cards cards-5">
            <section className="card stat-card" aria-label="Success rate">
              <p className="stat-label">Success rate</p>
              <p className="stat-value">{formatRate(period.success_rate_bps)}</p>
              <p className="stat-foot">
                {period.completed === 0
                  ? "No completed attempts to rate"
                  : `${formatCount(period.succeeded)} of ${formatCount(period.completed)} completed attempts succeeded`}
              </p>
              <p className="stat-foot">Baseline {formatRate(data.summary.baseline.success_rate_bps)} · {data.baseline_period.range_label}</p>
            </section>
            <section className="card stat-card" aria-label="Failed attempts">
              <p className="stat-label">Failed attempts</p>
              <p className="stat-value">{formatCount(period.failed)}</p>
              <p className="stat-foot">{periodFoot}</p>
              <p className="stat-foot">{period.pending > 0 ? `${formatCount(period.pending)} pending, not counted in the rate` : "No pending attempts"}</p>
            </section>
            <section className="card stat-card" aria-label="Affected payments">
              <p className="stat-label">Affected payments</p>
              <p className="stat-value">{formatCount(data.recovery.affected_payments)}</p>
              <p className="stat-foot">
                <Money cents={data.recovery.affected_cents} /> payment value
              </p>
              <p className="stat-foot">
                <Link to={paymentsDrill(scope, { recovery: "affected" })}>View affected payments</Link>
              </p>
            </section>
            <section className="card stat-card" aria-label="Recovered payments">
              <p className="stat-label">Recovered payments</p>
              <p className="stat-value">{formatCount(data.recovery.recovered_payments)}</p>
              <p className="stat-foot">
                <Money cents={data.recovery.recovered_cents} /> payment value
              </p>
              <p className="stat-foot">
                {formatCount(data.recovery.recovered_within_window)} within {data.thresholds.recovery_window_minutes} minutes of the first attempt
              </p>
            </section>
            <section className="card stat-card" aria-label="Unresolved payments">
              <p className="stat-label">Unresolved payments</p>
              <p className="stat-value">{formatCount(data.recovery.unresolved_payments)}</p>
              <p className="stat-foot">
                <Money cents={data.recovery.unresolved_cents} /> payment value
              </p>
              {data.recovery.unresolved_retry_pending > 0 ? (
                <p className="stat-foot">{formatCount(data.recovery.unresolved_retry_pending)} with a retry still pending</p>
              ) : null}
            </section>
          </div>

          <section className="card chart-card" aria-labelledby="health-chart-heading">
            <div className="section-head">
              <h2 id="health-chart-heading" className="section-title">
                Daily success rate
              </h2>
              <p className="muted section-aside">
                {periodFoot} · baseline {formatRate(data.summary.baseline.success_rate_bps)}
              </p>
            </div>
            <RateChart
              title={`Daily success rate, ${data.channel_label}, ${data.period.range_label}`}
              baselineBps={data.summary.baseline.success_rate_bps}
              formatRate={formatRate}
              points={data.daily.map((d) => ({
                label: formatDateShort(d.day),
                rateBps: d.success_rate_bps,
                lowVolume: d.low_volume,
                detail: dayDetail(d.success_rate_bps, d.succeeded, d.failed, d.pending, d.low_volume),
              }))}
            />
            <ul className="chart-legend">
              <li>
                <span className="legend-line" aria-hidden="true" /> Success rate
              </li>
              <li>
                <span className="legend-baseline" aria-hidden="true" /> Baseline, {data.baseline_period.range_label}
              </li>
              <li>
                <span className="legend-low" aria-hidden="true" /> Low volume (fewer than {data.thresholds.low_volume_day_completed} completed attempts)
              </li>
              <li>
                <span className="legend-gap" aria-hidden="true">
                  ×
                </span>{" "}
                No completed attempts
              </li>
            </ul>
          </section>

          <section aria-labelledby="health-channels-heading" className="health-section">
            <div className="section-head">
              <h2 id="health-channels-heading" className="section-title">
                Performance by channel
              </h2>
              {data.channel ? (
                <button type="button" className="btn btn-sm" onClick={() => onScopeChannel(null)}>
                  Show all channels
                </button>
              ) : null}
            </div>
            <ChannelTable channels={data.channels} selected={data.channel} onSelect={onScopeChannel} />
          </section>
          <section aria-labelledby="health-signals-heading" className="health-section">
            <div className="section-head">
              <h2 id="health-signals-heading" className="section-title">
                Recorded failure signals
              </h2>
            </div>
            <p className="muted section-note">What each failed attempt recorded. These are signals to investigate, not confirmed root causes.</p>
            <SignalTable signals={data.failure_signals} scope={scope} />
          </section>

          <section aria-labelledby="health-unresolved-heading" className="health-section">
            <div className="section-head">
              <h2 id="health-unresolved-heading" className="section-title">
                Unresolved payments
              </h2>
              {data.recovery.unresolved_payments > 0 ? (
                <Link to={paymentsDrill(scope, { recovery: "unresolved" })} className="section-aside">
                  Review all {formatCount(data.recovery.unresolved_payments)} in Payments
                </Link>
              ) : null}
            </div>
            <UnresolvedTable rows={data.unresolved} total={data.recovery.unresolved_payments} />
          </section>
        </>
      )}

      <Definitions data={data} />
    </div>
  );
}

function dayDetail(rate: number | null, succeeded: number, failed: number, pending: number, lowVolume: boolean): string {
  const counts = `${formatCount(succeeded)} succeeded, ${formatCount(failed)} failed, ${formatCount(pending)} pending`;
  if (rate === null) return `no completed attempts (${counts})`;
  return `${formatRate(rate)} (${counts})${lowVolume ? ", low volume" : ""}`;
}

function channelEvidence(c: ChannelHealth): string {
  const drop = c.drop_bps !== null ? `, ${formatPoints(c.drop_bps)} below` : "";
  return `${formatRate(c.period.success_rate_bps)} success against a ${formatRate(c.baseline.success_rate_bps)} baseline${drop}; ${formatCount(c.period.failed)} failed attempts`;
}

function AttentionSummary({ data, scope }: { data: PaymentHealth; scope: HealthScope }) {
  const { attention, thresholds } = data;
  const pending = data.summary.period.pending;
  const tone = attention.status === "degraded" ? "danger" : attention.status === "not_degraded" ? "success" : "neutral";
  return (
    <section className={`card health-attention health-attention-${tone}`} aria-labelledby="health-attention-heading" role="status">
      <h2 id="health-attention-heading" className="section-title">
        <StatusBadge status={attention.status} label={attentionHeadline(data)} />
      </h2>
      {attention.status === "degraded" ? (
        <ul className="health-attention-list">
          {attention.degraded.map((c) => (
            <li key={c.channel}>
              <strong>{c.channel_label}</strong>: {channelEvidence(c)}.{" "}
              <Link to={paymentsDrill({ ...scope, channel: c.channel }, { recovery: "unresolved" })}>Review unresolved {c.channel_label.toLowerCase()} payments</Link>
            </li>
          ))}
        </ul>
      ) : null}
      {attention.status === "not_degraded" ? (
        <p className="muted">
          No significant degradation detected: every evaluated channel is less than {formatPoints(thresholds.degraded_drop_bps)} below its own baseline.
        </p>
      ) : null}
      {attention.status === "insufficient_volume" ? (
        <p className="muted">
          There are not enough completed attempts to draw a conclusion. A channel is evaluated with at least {formatCount(thresholds.min_period_completed)} completed attempts in the
          period and {formatCount(thresholds.min_baseline_completed)} in its baseline.
        </p>
      ) : null}
      {attention.status === "no_completed" ? <p className="muted">No attempts completed in this period, so there is no success rate to compare.</p> : null}
      {attention.not_evaluated.length > 0 ? (
        <p className="muted">
          Not evaluated:{" "}
          {attention.not_evaluated
            .map((c) => `${c.channel_label} (${formatCount(c.period.completed)} completed in the period, ${formatCount(c.baseline.completed)} in the baseline)`)
            .join("; ")}
          .
        </p>
      ) : null}
      {pending > 0 ? (
        <p className="muted">
          {pending === 1 ? "1 attempt is still pending; it is" : `${formatCount(pending)} attempts are still pending; they are`} not counted in any success rate.
        </p>
      ) : null}
    </section>
  );
}

function attentionHeadline(data: PaymentHealth): string {
  const { attention } = data;
  if (attention.status === "degraded") {
    const names = attention.degraded.map((c) => c.channel_label);
    return `Degraded: ${names.join(", ")}`;
  }
  return attention.status_label;
}

function ChannelTable({ channels, selected, onSelect }: { channels: ChannelHealth[]; selected: string | null; onSelect: (channel: string) => void }) {
  const columns: Column<ChannelHealth>[] = [
    {
      key: "channel",
      header: "Channel",
      className: "primary",
      render: (c) => (
        <button
          type="button"
          className="link-button"
          aria-pressed={c.channel === selected}
          aria-label={`Scope the page to ${c.channel_label}`}
          onClick={(e) => {
            e.stopPropagation();
            onSelect(c.channel);
          }}
        >
          {c.channel_label}
        </button>
      ),
    },
    { key: "rate", header: "Success rate", align: "right", render: (c) => formatRate(c.period.success_rate_bps) },
    { key: "baseline", header: "Baseline", align: "right", render: (c) => formatRate(c.baseline.success_rate_bps) },
    { key: "completed", header: "Completed", align: "right", render: (c) => formatCount(c.period.completed) },
    { key: "failed", header: "Failed", align: "right", render: (c) => formatCount(c.period.failed) },
    { key: "pending", header: "Pending", align: "right", render: (c) => formatCount(c.period.pending) },
    { key: "evaluation", header: "Evaluation", render: (c) => <StatusBadge status={c.evaluation} label={c.evaluation_label} /> },
  ];
  if (channels.length === 0) return <EmptyState title="No channel activity" body="No attempts in this period or its baseline." />;
  return (
    <DataTable
      caption="Performance by channel"
      columns={columns}
      rows={channels}
      rowKey={(c) => c.channel}
      onRowClick={(c) => onSelect(c.channel)}
      rowClassName={(c) => (c.channel === selected ? "row-selected" : undefined)}
    />
  );
}

function SignalTable({ signals, scope }: { signals: FailureSignal[]; scope: HealthScope }) {
  const navigate = useNavigate();
  const href = (s: FailureSignal) => attemptsDrill(scope, { outcome: "failed", failure_code: s.code });
  const columns: Column<FailureSignal>[] = [
    {
      key: "signal",
      header: "Recorded signal",
      className: "primary",
      render: (s) => (
        <Link to={href(s)} className="row-link" onClick={(e) => e.stopPropagation()}>
          {s.label}
        </Link>
      ),
    },
    { key: "failed", header: "Failed attempts", align: "right", render: (s) => formatCount(s.failed_attempts) },
  ];
  if (signals.length === 0) return <EmptyState title="No failed attempts" body="Nothing failed in this period." />;
  return <DataTable caption="Recorded failure signals" columns={columns} rows={signals} rowKey={(s) => s.code} onRowClick={(s) => navigate(href(s))} />;
}

function UnresolvedTable({ rows, total }: { rows: UnresolvedPayment[]; total: number }) {
  const navigate = useNavigate();
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
    { key: "failed", header: "Failed attempts", align: "right", render: (p) => formatCount(p.failed_attempts) },
    { key: "signal", header: "Last recorded signal", render: (p) => p.last_failure_label },
    { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} label={p.status_label} /> },
    { key: "amount", header: "Amount", align: "right", render: (p) => <Money cents={p.amount_cents} /> },
  ];
  if (rows.length === 0) return <EmptyState title="No unresolved payments" body="Every payment with a failed attempt in this period later succeeded." />;
  return (
    <>
      <DataTable caption="Unresolved payments" columns={columns} rows={rows} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/payments/${p.id}`)} />
      {total > rows.length ? <p className="muted section-note">Showing the {rows.length} most recent of {formatCount(total)}.</p> : null}
    </>
  );
}

function Definitions({ data }: { data: PaymentHealth }) {
  const t: HealthThresholds = data.thresholds;
  return (
    <section className="card health-section" aria-labelledby="health-definitions-heading">
      <h2 id="health-definitions-heading" className="section-title">
        How Payment Health is calculated
      </h2>
      <DescriptionList
        columns={2}
        items={[
          { term: "Success rate", value: "Succeeded attempts ÷ (succeeded + failed attempts) created in the period. Pending attempts are counted separately and never in the rate." },
          { term: "Baseline", value: `The same channel's success rate over the ${t.baseline_days} days before the period (${data.baseline_period.range_label}).` },
          {
            term: "Degraded",
            value: `A channel whose success rate is at least ${formatPoints(t.degraded_drop_bps)} below its baseline. It is only evaluated with at least ${formatCount(t.min_period_completed)} completed attempts in the period and ${formatCount(t.min_baseline_completed)} in the baseline.`,
          },
          { term: "Low-volume day", value: `A day with fewer than ${formatCount(t.low_volume_day_completed)} completed attempts.` },
          { term: "Affected", value: "A payment created in the period with at least one failed attempt. Its value is the payment amount, counted once." },
          { term: "Recovered", value: `An affected payment that later succeeded on a retry, counted once however many attempts failed first. Recoveries within ${t.recovery_window_minutes} minutes of the first attempt are shown separately.` },
          { term: "Unresolved", value: "An affected payment with no successful attempt. Its value is a payment amount, not a loss." },
          { term: "Recorded failure signal", value: "The reason recorded on a failed attempt. It is evidence to investigate, not a confirmed root cause." },
        ]}
      />
      <p className="muted section-note">
        Attempt figures use when each attempt was made; payment figures use when the payment was created. A retry after midnight can fall on a different day from its payment.
      </p>
    </section>
  );
}
