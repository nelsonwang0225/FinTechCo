import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { AttemptStats, ChannelHealth, FailureSignal, HealthRules, PaymentHealth } from "../../api/payment-health-types";
import type { PaymentListItem } from "../../api/payments-types";
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
import { formatCount, formatDateShort, formatPointsBps, formatRateBps } from "../../lib/format";
import { useQueryState, type QueryState } from "../../lib/query";
import { PeriodFilter } from "../payments/PeriodFilter";
import { drillHref, healthScope } from "./scope";

export function PaymentHealthPage() {
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const health = useApi<PaymentHealth>(`/api/payment-health${queryString(healthScope(query))}`);
  const data = health.data;

  return (
    <>
      <PageHeader
        title="Payment health"
        subtitle="Completed-attempt performance by channel against its own baseline, and what happened to the payments affected. Times are shown in America/Chicago."
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
      {data ? <HealthBody data={data} query={query} loading={health.loading} /> : null}
    </>
  );
}

function HealthBody({ data, query, loading }: { data: PaymentHealth; query: QueryState; loading: boolean }) {
  const scopeLabel = data.channel_label ?? "All channels";
  const period = data.summary.period;
  return (
    <div className={loading ? "health overview-loading" : "health"} aria-busy={loading || undefined}>
      <AttentionSummary data={data} query={query} />

      <div className="section-head">
        <h2 className="section-title">
          {scopeLabel} · {data.period.range_label}
        </h2>
        <p className="muted section-aside">
          Baseline: {data.baseline.range_label}
        </p>
      </div>

      {period.completed === 0 ? (
        <EmptyState
          title="No completed attempts in this scope"
          body={
            period.pending > 0
              ? `${formatCount(period.pending)} pending ${plural(period.pending, "attempt is", "attempts are")} still waiting for an outcome, so there is no success rate to show.`
              : "No attempt finished in this period and channel, so there is no success rate to show. Try a wider period or another channel."
          }
        />
      ) : (
        <>
          <AttemptTiles data={data} query={query} />
          <section className="card chart-card" aria-labelledby="health-trend-heading">
            <div className="section-head">
              <h2 id="health-trend-heading" className="section-title">
                Daily success rate
              </h2>
              <p className="muted section-aside">Completed attempts by the day they were made</p>
            </div>
            <RateChart
              title={`Daily completed-attempt success rate, ${scopeLabel}, ${data.period.range_label}`}
              points={data.trend.map((p) => ({ label: formatDateShort(p.day), rateBps: p.success_rate_bps, lowVolume: p.low_volume, detail: countsDetail(p) }))}
              baselineBps={data.summary.baseline.success_rate_bps}
              baselineLabel={`Baseline, ${data.baseline.range_label}`}
              formatRate={formatRateBps}
            />
            <ul className="chart-legend" aria-label="Chart key">
              <li>
                <span className="legend-swatch legend-line" aria-hidden="true" />
                Success rate
              </li>
              <li>
                <span className="legend-swatch legend-baseline" aria-hidden="true" />
                Baseline {formatRateBps(data.summary.baseline.success_rate_bps)} (previous {data.rules.baseline_days} days)
              </li>
              <li>
                <span className="legend-swatch legend-low" aria-hidden="true" />
                Low volume: fewer than {data.rules.low_volume_day_completed} completed attempts
              </li>
              <li>
                <span className="legend-swatch legend-gap" aria-hidden="true" />
                Gap: no completed attempts that day
              </li>
            </ul>
          </section>
        </>
      )}

      <section aria-labelledby="health-channels-heading" className="health-section">
        <div className="section-head">
          <h2 id="health-channels-heading" className="section-title">
            Performance by channel
          </h2>
          {data.channel ? (
            <Link to={`?${channelSearch(query, null)}`} className="section-aside">
              Show all channels
            </Link>
          ) : (
            <p className="muted section-aside">Select a channel to scope the page to it</p>
          )}
        </div>
        <ChannelTable data={data} query={query} />
      </section>

      <section aria-labelledby="health-signals-heading" className="health-section">
        <div className="section-head">
          <h2 id="health-signals-heading" className="section-title">
            Recorded failure signals
          </h2>
          <p className="muted section-aside">The codes recorded on failed attempts, not confirmed root causes</p>
        </div>
        <SignalTable signals={data.failure_signals} query={query} />
      </section>

      <RecoverySection data={data} query={query} />

      <section aria-labelledby="health-unresolved-heading" className="health-section">
        <div className="section-head">
          <h2 id="health-unresolved-heading" className="section-title">
            Unresolved payments
          </h2>
          {data.unresolved_payments.total > 0 ? (
            <Link to={drillHref(query, { status: "failed" })} className="section-aside">
              Review all {formatCount(data.unresolved_payments.total)} in Payments
            </Link>
          ) : null}
        </div>
        <UnresolvedTable items={data.unresolved_payments.items} total={data.unresolved_payments.total} />
      </section>

      <Definitions rules={data.rules} />
    </div>
  );
}

/** Whether any channel is degraded, with the evidence, or plainly that none is, or that nothing could be evaluated. */
function AttentionSummary({ data, query }: { data: PaymentHealth; query: QueryState }) {
  const degraded = data.channels.filter((c) => c.assessment === "degraded");
  const evaluated = data.channels.filter((c) => c.assessment === "degraded" || c.assessment === "normal");
  const notEvaluated = data.channels.filter((c) => c.assessment === "insufficient_data" || c.assessment === "no_attempts");
  const tone = degraded.length > 0 ? "danger" : evaluated.length > 0 ? "success" : "neutral";
  return (
    <section className={`card health-attention health-attention-${tone}`} aria-labelledby="health-attention-heading">
      <h2 id="health-attention-heading" className="section-title">
        {degraded.length > 0
          ? `${joinLabels(degraded)} ${degraded.length === 1 ? "is" : "are"} degraded`
          : evaluated.length > 0
            ? "No significant degradation detected"
            : "Not enough data to assess channel health"}
      </h2>
      {degraded.length > 0 ? (
        <ul className="health-attention-list">
          {degraded.map((c) => (
            <li key={c.channel}>
              <p className="attention-title">
                <StatusBadge status={c.assessment} label={c.assessment_label} /> {c.label}: {formatRateBps(c.period.success_rate_bps)} success against a baseline of{" "}
                {formatRateBps(c.baseline.success_rate_bps)} ({formatPointsBps(c.delta_bps)}), {formatCount(c.period.failed)} failed{" "}
                {plural(c.period.failed, "attempt", "attempts")}.
              </p>
              <p className="attention-detail">
                <Link to={drillHref(query, { status: "failed", channel: c.channel })}>Review unresolved {c.label.toLowerCase()} payments</Link>
                {" · "}
                <Link to={drillHref(query, { tab: "attempts", outcome: "failed", channel: c.channel })}>View failed attempts</Link>
              </p>
            </li>
          ))}
        </ul>
      ) : evaluated.length > 0 ? (
        <p className="attention-detail">
          {evaluated.length === 1 ? `${evaluated[0].label} did not fall` : `None of ${joinLabels(evaluated)} fell`} {formatPointsBps(data.rules.degraded_drop_bps, { signed: false })} or more
          below {evaluated.length === 1 ? "its" : "their own"} baseline.
        </p>
      ) : (
        <p className="attention-detail">No channel had enough completed attempts in this period and its baseline to draw a conclusion.</p>
      )}
      {notEvaluated.length > 0 ? (
        <ul className="health-not-evaluated">
          {notEvaluated.map((c) => (
            <li key={c.channel}>
              <StatusBadge status={c.assessment} label={c.assessment_label} /> {c.label}: {notEvaluatedReason(c, data.rules)}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function notEvaluatedReason(c: ChannelHealth, rules: HealthRules): string {
  if (c.assessment === "no_attempts") return "no completed attempts in this period.";
  return `${formatCount(c.period.completed)} completed ${plural(c.period.completed, "attempt", "attempts")} in this period and ${formatCount(c.baseline.completed)} in the baseline; at least ${rules.min_period_completed} and ${rules.min_baseline_completed} are needed.`;
}

function AttemptTiles({ data, query }: { data: PaymentHealth; query: QueryState }) {
  const { period, baseline } = data.summary;
  return (
    <div className="cards cards-4">
      <section className="card stat-card" aria-label="Success rate">
        <p className="stat-label">Success rate</p>
        <p className="stat-value">{formatRateBps(period.success_rate_bps)}</p>
        <p className="stat-foot">
          Baseline {formatRateBps(baseline.success_rate_bps)} · {formatPointsBps(data.summary.delta_bps)}
        </p>
        <p className="stat-foot">
          {formatCount(period.succeeded)} of {formatCount(period.completed)} completed {plural(period.completed, "attempt", "attempts")} succeeded
        </p>
      </section>
      <section className="card stat-card" aria-label="Failed attempts">
        <p className="stat-label">Failed attempts</p>
        <p className="stat-value">{formatCount(period.failed)}</p>
        <p className="stat-foot">Baseline: {formatCount(baseline.failed)} over {data.rules.baseline_days} days</p>
        {period.failed > 0 ? (
          <p className="stat-foot">
            <Link to={drillHref(query, { tab: "attempts", outcome: "failed" })}>View failed attempts</Link>
          </p>
        ) : null}
      </section>
      <section className="card stat-card" aria-label="Completed attempts">
        <p className="stat-label">Completed attempts</p>
        <p className="stat-value">{formatCount(period.completed)}</p>
        <p className="stat-foot">Succeeded or failed; the success rate's denominator</p>
      </section>
      <section className="card stat-card" aria-label="Pending attempts">
        <p className="stat-label">Pending attempts</p>
        <p className="stat-value">{formatCount(period.pending)}</p>
        <p className="stat-foot">Waiting for an outcome; not counted in the success rate</p>
      </section>
    </div>
  );
}

function ChannelTable({ data, query }: { data: PaymentHealth; query: QueryState }) {
  const columns: Column<ChannelHealth>[] = [
    {
      key: "channel",
      header: "Channel",
      className: "primary",
      render: (c) => (
        <Link
          to={`?${channelSearch(query, c.channel)}`}
          className="row-link channel-link"
          aria-current={data.channel === c.channel ? "true" : undefined}
          aria-label={`Scope the page to ${c.label}`}
        >
          {c.label}
        </Link>
      ),
    },
    { key: "rate", header: "Success rate", align: "right", render: (c) => formatRateBps(c.period.success_rate_bps) },
    { key: "baseline", header: "Baseline", align: "right", render: (c) => formatRateBps(c.baseline.success_rate_bps) },
    { key: "delta", header: "Change", align: "right", render: (c) => formatPointsBps(c.delta_bps) },
    { key: "completed", header: "Completed", align: "right", render: (c) => formatCount(c.period.completed) },
    { key: "failed", header: "Failed", align: "right", render: (c) => formatCount(c.period.failed) },
    { key: "pending", header: "Pending", align: "right", render: (c) => formatCount(c.period.pending) },
    { key: "assessment", header: "Assessment", render: (c) => <StatusBadge status={c.assessment} label={c.assessment_label} /> },
  ];
  return <DataTable caption="Performance by channel" columns={columns} rows={data.channels} rowKey={(c) => c.channel} />;
}

function SignalTable({ signals, query }: { signals: FailureSignal[]; query: QueryState }) {
  if (signals.length === 0) return <EmptyState title="No failed attempts recorded" body="No attempt in this period and channel failed, so there are no failure signals to break down." />;
  const columns: Column<FailureSignal>[] = [
    { key: "label", header: "Recorded signal", className: "primary", render: (s) => s.label },
    { key: "code", header: "Code", className: "secondary", render: (s) => <span className="mono">{s.failure_code}</span> },
    {
      key: "failed",
      header: "Failed attempts",
      align: "right",
      render: (s) => (
        <Link to={drillHref(query, { tab: "attempts", outcome: "failed", failure_code: s.failure_code })} aria-label={`${formatCount(s.failed_attempts)} failed attempts recorded as ${s.label}`}>
          {formatCount(s.failed_attempts)}
        </Link>
      ),
    },
  ];
  return <DataTable caption="Recorded failure signals" columns={columns} rows={signals} rowKey={(s) => s.failure_code} />;
}

function RecoverySection({ data, query }: { data: PaymentHealth; query: QueryState }) {
  const r = data.recovery;
  const windowText = windowLabel(data.rules.recovery_window_seconds);
  return (
    <section aria-labelledby="health-recovery-heading" className="health-section">
      <div className="section-head">
        <h2 id="health-recovery-heading" className="section-title">
          Recovery by payment
        </h2>
        <p className="muted section-aside">Payments created in this period, each counted once at its payment amount</p>
      </div>
      {r.affected_payments === 0 ? (
        <EmptyState title="No affected payments" body="No payment created in this period and channel had a failed attempt." />
      ) : (
        <div className="cards cards-4">
          <section className="card stat-card" aria-label="Affected payments">
            <p className="stat-label">Affected payments</p>
            <p className="stat-value">{formatCount(r.affected_payments)}</p>
            <p className="stat-foot">
              <Money cents={r.affected_cents} /> in payment amounts
            </p>
            <p className="stat-foot">At least one failed attempt</p>
          </section>
          <section className="card stat-card" aria-label="Recovered payments">
            <p className="stat-label">Recovered</p>
            <p className="stat-value">{formatCount(r.recovered_payments)}</p>
            <p className="stat-foot">
              <Money cents={r.recovered_cents} /> in payment amounts
            </p>
            <p className="stat-foot">
              {formatCount(r.recovered_within_window_payments)} within {windowText} of the first attempt
            </p>
          </section>
          <section className="card stat-card" aria-label="Unresolved payments">
            <p className="stat-label">Unresolved</p>
            <p className="stat-value">{formatCount(r.unresolved_payments)}</p>
            <p className="stat-foot">
              <Money cents={r.unresolved_cents} /> in payment amounts
            </p>
            {r.unresolved_payments > 0 ? (
              <p className="stat-foot">
                <Link to={drillHref(query, { status: "failed" })}>Review in Payments</Link>
              </p>
            ) : null}
          </section>
          <section className="card stat-card" aria-label="Retry pending">
            <p className="stat-label">Retry pending</p>
            <p className="stat-value">{formatCount(r.retry_pending_payments)}</p>
            <p className="stat-foot">
              <Money cents={r.retry_pending_cents} /> in payment amounts
            </p>
            <p className="stat-foot">Failed before; latest attempt still pending</p>
          </section>
        </div>
      )}
    </section>
  );
}

function UnresolvedTable({ items, total }: { items: PaymentListItem[]; total: number }) {
  const navigate = useNavigate();
  if (items.length === 0) return <EmptyState title="No unresolved payments" body="Every payment in this scope that had a failed attempt has since succeeded or is still being retried." />;
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
    { key: "method", header: "Last method", render: (p) => p.method?.label ?? <span className="muted">—</span> },
    { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} label={p.status_label} /> },
    { key: "amount", header: "Amount", align: "right", render: (p) => <Money cents={p.amount_cents} /> },
  ];
  return (
    <>
      <DataTable caption="Unresolved payments" columns={columns} rows={items} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/payments/${p.id}`)} />
      {total > items.length ? (
        <p className="muted health-more">
          Showing the {formatCount(items.length)} most recent of {formatCount(total)}.
        </p>
      ) : null}
    </>
  );
}

function Definitions({ rules }: { rules: HealthRules }) {
  const windowText = windowLabel(rules.recovery_window_seconds);
  const drop = formatPointsBps(rules.degraded_drop_bps, { signed: false });
  const terms: [string, string][] = [
    ["Success rate", "Succeeded attempts divided by completed attempts (succeeded plus failed). Pending attempts are left out and counted separately."],
    ["Period", "Attempts count toward the day they were made, as on the Attempts tab. Payments count toward the day they were created, as on the Payments list."],
    ["Baseline", `The same channel's success rate over the ${rules.baseline_days} days before the selected period, from the attempts recorded in those days.`],
    [
      "Degraded",
      `A channel's success rate is ${drop} or more below its own baseline. A channel is evaluated only with at least ${rules.min_period_completed} completed attempts in the period and ${rules.min_baseline_completed} in the baseline; otherwise the page says there is not enough data. The rule is fixed; no statistical model is used.`,
    ],
    ["Low-volume day", `A day with fewer than ${rules.low_volume_day_completed} completed attempts. Its rate is shown but can swing on a handful of attempts.`],
    ["Affected payment", "A payment created in the period with at least one failed attempt. Each payment counts once, at its payment amount, however many attempts it had."],
    ["Recovered", `An affected payment that later succeeded. "Within ${windowText}" means the successful attempt completed within ${windowText} of the payment's first attempt.`],
    ["Unresolved", "An affected payment with no successful attempt whose latest attempt failed. This is the payment status Failed."],
    ["Retry pending", "An affected payment with no successful attempt whose latest attempt is still pending."],
    ["Recorded failure signal", "The failure code recorded on a failed attempt. It describes what was reported, not a confirmed root cause."],
    ["Amounts", "Affected, recovered, unresolved and retry-pending amounts are the payment amounts of those payments, each counted once."],
  ];
  return (
    <details className="card health-definitions">
      <summary>How Payment Health is calculated</summary>
      <dl>
        {terms.map(([term, text]) => (
          <div key={term} className="health-definition">
            <dt>{term}</dt>
            <dd>{text}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

/** The current URL with the channel set (or cleared) and the page reset, for a row that scopes the page. */
function channelSearch(query: QueryState, channel: string | null): string {
  const next = new URLSearchParams(query.search);
  if (channel) next.set("channel", channel);
  else next.delete("channel");
  next.delete("page");
  return next.toString();
}

function countsDetail(p: AttemptStats): string {
  return `${formatCount(p.succeeded)} succeeded, ${formatCount(p.failed)} failed, ${formatCount(p.pending)} pending`;
}

function windowLabel(seconds: number): string {
  if (seconds % 3600 === 0) return `${seconds / 3600} ${seconds === 3600 ? "hour" : "hours"}`;
  return `${Math.round(seconds / 60)} minutes`;
}

function joinLabels(channels: ChannelHealth[]): string {
  const labels = channels.map((c) => c.label);
  return labels.length <= 1 ? labels.join("") : `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
}

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}
