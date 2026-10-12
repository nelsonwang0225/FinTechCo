import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { ChannelHealth, FailureSignal, HealthRules, PaymentHealth } from "../../api/payment-health-types";
import type { PaymentListItem, PaymentListResponse } from "../../api/payments-types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { DescriptionList } from "../../components/DescriptionList";
import { Money } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { formatCents, formatCount, formatPointChange, formatPoints, formatRate } from "../../lib/format";
import { attemptsLink, paymentsLink, type Scope } from "../../lib/healthLinks";

const UNRESOLVED_SHOWN = 10;

function listNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export function AttentionSummary({ data, scope, returnTo }: { data: PaymentHealth; scope: Scope; returnTo: string }) {
  const { attention, rules } = data;
  const byChannel = new Map(data.channels.map((c) => [c.channel, c]));
  const degraded = attention.degraded_channels.flatMap((c) => byChannel.get(c) ?? []);
  const notAssessed = attention.not_assessed_channels.flatMap((c) => byChannel.get(c)?.channel_label ?? []);
  const period = { ...scope, channel: undefined };
  return (
    <section className={`card health-attention health-attention-${attention.state}`} aria-labelledby="health-attention-heading">
      <h2 id="health-attention-heading" className="section-title">
        <StatusBadge status={attention.state} label={attention.label} />
      </h2>
      {degraded.length > 0 ? (
        <ul className="attention-list">
          {degraded.map((c) => (
            <li key={c.channel} className="attention-item attention-degraded">
              <span className="attention-dot" aria-hidden="true" />
              <div className="attention-body">
                <p className="attention-title">
                  {c.channel_label}: {formatRate(c.success_rate_bp)} success against a {formatRate(c.baseline_rate_bp)} baseline ({formatPointChange(c.change_bp)})
                </p>
                <p className="attention-detail muted">
                  {formatCount(c.failed)} failed of {formatCount(c.completed)} completed attempts in this period; baseline from {formatCount(c.baseline_completed)} completed attempts.
                </p>
                <p className="attention-when">
                  <Link to={paymentsLink({ ...period, channel: c.channel }, { status: "failed" }, returnTo)}>Review unresolved {c.channel_label.toLowerCase()} payments</Link>
                  {" · "}
                  <Link to={attemptsLink({ ...period, channel: c.channel }, { outcome: "failed" }, returnTo)}>View failed attempts</Link>
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {attention.state === "no_significant_degradation" ? (
        <p className="attention-empty">
          No assessed channel's success rate is {formatPoints(rules.degraded_drop_bp)} or more below its baseline.
        </p>
      ) : null}
      {attention.state === "insufficient_data" ? (
        <p className="attention-empty">
          No channel has enough completed attempts in this period ({rules.min_period_completed}) and its baseline ({rules.min_baseline_completed}) to draw a conclusion.
        </p>
      ) : null}
      {attention.state === "no_completed_attempts" ? <p className="attention-empty">There are no completed attempts to assess in this period.</p> : null}
      {notAssessed.length > 0 && attention.state !== "insufficient_data" ? (
        <p className="attention-empty muted">
          Not assessed for lack of volume: {listNames(notAssessed)}.
        </p>
      ) : null}
    </section>
  );
}

export function ChannelTable({ data, onChannel }: { data: PaymentHealth; onChannel: (channel: string | null) => void }) {
  const selected = data.channel;
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
            onChannel(selected === c.channel ? null : c.channel);
          }}
        >
          {c.channel_label}
        </button>
      ),
    },
    { key: "assessment", header: "Assessment", render: (c) => <StatusBadge status={c.assessment} label={c.assessment_label} /> },
    { key: "rate", header: "Success rate", align: "right", render: (c) => formatRate(c.success_rate_bp) },
    { key: "baseline", header: "Baseline", align: "right", render: (c) => formatRate(c.baseline_rate_bp) },
    { key: "change", header: "Change", align: "right", render: (c) => formatPointChange(c.change_bp) },
    { key: "completed", header: "Completed", align: "right", render: (c) => formatCount(c.completed) },
    { key: "failed", header: "Failed", align: "right", render: (c) => formatCount(c.failed) },
    { key: "pending", header: "Pending", align: "right", render: (c) => formatCount(c.pending) },
  ];
  return (
    <section className="card health-channels" aria-labelledby="channels-heading">
      <div className="section-head">
        <h2 id="channels-heading" className="section-title">
          Performance by channel
        </h2>
        {selected ? (
          <button type="button" className="link-button section-aside" onClick={() => onChannel(null)}>
            Show all channels
          </button>
        ) : (
          <p className="muted section-aside">Select a channel to scope the page</p>
        )}
      </div>
      {data.channels.length === 0 ? (
        <EmptyState title="No channel activity" body="No attempts were made in this period or its baseline." />
      ) : (
        <DataTable
          caption="Performance by channel"
          columns={columns}
          rows={data.channels}
          rowKey={(c) => c.channel}
          onRowClick={(c) => onChannel(selected === c.channel ? null : c.channel)}
          rowClassName={(c) => (selected === c.channel ? "row-selected" : undefined)}
        />
      )}
    </section>
  );
}

export function FailureSignals({ data, scope, returnTo }: { data: PaymentHealth; scope: Scope; returnTo: string }) {
  const columns: Column<FailureSignal>[] = [
    { key: "signal", header: "Recorded signal", className: "primary", render: (s) => s.label },
    {
      key: "count",
      header: "Failed attempts",
      align: "right",
      render: (s) => (
        <Link to={attemptsLink(scope, { outcome: "failed", failure_code: s.code }, returnTo)} aria-label={`${formatCount(s.count)} failed attempts recorded as ${s.label}`}>
          {formatCount(s.count)}
        </Link>
      ),
    },
  ];
  return (
    <section className="card" aria-labelledby="signals-heading">
      <div className="section-head">
        <h2 id="signals-heading" className="section-title">
          Recorded failure signals
        </h2>
        <p className="muted section-aside">{formatCount(data.attempts.failed)} failed attempts</p>
      </div>
      <p className="muted health-note">The failure code recorded on each failed attempt. These are signals to investigate, not confirmed root causes.</p>
      {data.failure_signals.length === 0 ? (
        <EmptyState title="No failed attempts" body="Nothing failed in this period and channel." />
      ) : (
        <DataTable caption="Recorded failure signals" columns={columns} rows={data.failure_signals} rowKey={(s) => s.code} />
      )}
    </section>
  );
}

function GroupValue({ count, cents }: { count: number; cents: number }) {
  return (
    <>
      <span className="health-group-count">
        {formatCount(count)} payment{count === 1 ? "" : "s"}
      </span>
      <span className="muted"> · {formatCents(cents)}</span>
    </>
  );
}

export function RecoveryPanel({ data, scope, returnTo }: { data: PaymentHealth; scope: Scope; returnTo: string }) {
  const r = data.recovery;
  const minutes = Math.round(data.rules.quick_recovery_seconds / 60);
  return (
    <section className="card health-recovery" aria-labelledby="recovery-heading">
      <div className="section-head">
        <h2 id="recovery-heading" className="section-title">
          Recovery by payment
        </h2>
        <p className="muted section-aside">Payments created in this period with at least one failed attempt</p>
      </div>
      <DescriptionList
        columns={4}
        items={[
          { term: "Affected", value: <GroupValue count={r.affected.payments} cents={r.affected.amount_cents} /> },
          {
            term: "Recovered",
            value: (
              <>
                <GroupValue count={r.recovered.payments} cents={r.recovered.amount_cents} />
                <span className="health-subvalue muted">
                  {formatCount(r.recovered_within_hour.payments)} within {minutes === 60 ? "1 hour" : `${minutes} minutes`} of the first attempt
                </span>
              </>
            ),
          },
          { term: "Unresolved", value: <GroupValue count={r.unresolved.payments} cents={r.unresolved.amount_cents} /> },
          { term: "Retry in progress", value: <GroupValue count={r.in_progress.payments} cents={r.in_progress.amount_cents} /> },
        ]}
      />
      <p className="muted health-note">Amounts are payment amounts, each counted once however many attempts it took.</p>
      <UnresolvedPayments scope={scope} returnTo={returnTo} expected={r.unresolved.payments} />
    </section>
  );
}

function UnresolvedPayments({ scope, returnTo, expected }: { scope: Scope; returnTo: string; expected: number }) {
  const navigate = useNavigate();
  const list = useApi<PaymentListResponse>(
    expected > 0 ? `/api/payments${queryString({ ...scope, status: "failed", sort: "created_at", dir: "desc", page_size: UNRESOLVED_SHOWN })}` : null,
  );
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
    <div className="health-unresolved">
      <div className="section-head">
        <h3 className="section-title">Unresolved payments</h3>
        {expected > 0 ? (
          <Link to={paymentsLink(scope, { status: "failed" }, returnTo)} className="section-aside">
            Review all {formatCount(expected)} in Payments
          </Link>
        ) : null}
      </div>
      {expected === 0 ? <p className="muted attention-empty">Every affected payment has recovered or is still being retried.</p> : null}
      {list.error ? <LoadError error={list.error} onRetry={list.reload} /> : null}
      {expected > 0 && !list.error && !list.data ? <LoadingState rows={3} label="Loading unresolved payments" /> : null}
      {list.data ? (
        <DataTable caption="Unresolved payments" columns={columns} rows={list.data.items} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/payments/${p.id}`)} loading={list.loading} />
      ) : null}
    </div>
  );
}

export function Definitions({ rules }: { rules: HealthRules }) {
  const drop = formatPoints(rules.degraded_drop_bp);
  return (
    <section className="card health-definitions" aria-labelledby="definitions-heading">
      <h2 id="definitions-heading" className="section-title">
        How these figures are defined
      </h2>
      <DescriptionList
        columns={2}
        items={[
          { term: "Success rate", value: "Succeeded attempts divided by completed attempts (succeeded plus failed), by the time each attempt was made. Pending attempts are counted separately and left out of the rate." },
          { term: "Baseline", value: `The same channel's success rate over the ${rules.baseline_days} days before the selected period.` },
          {
            term: "Degraded",
            value: `A channel whose success rate is ${drop} or more below its baseline, when the period has at least ${rules.min_period_completed} completed attempts and the baseline at least ${rules.min_baseline_completed}. With fewer, the channel is not assessed. Days with fewer than ${rules.low_volume_day_completed} completed attempts are marked low volume on the chart.`,
          },
          { term: "Affected", value: "A payment created in the period with at least one failed attempt, counted once whatever its number of attempts." },
          { term: "Recovered", value: "An affected payment that later succeeded on a retry." },
          { term: "Unresolved", value: "An affected payment whose attempts all failed: its status is Failed." },
          { term: "Retry in progress", value: "An affected payment whose latest attempt is still pending." },
          { term: "Recorded failure signal", value: "The failure code recorded on a failed attempt. It describes what was reported, not a confirmed root cause." },
        ]}
      />
    </section>
  );
}
