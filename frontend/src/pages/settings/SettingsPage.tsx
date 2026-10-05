import { Link } from "react-router-dom";
import { queryString } from "../../api/client";
import type { ActivityItem, ActivityResponse, BusinessProfile, TeamMember, TeamResponse } from "../../api/settings-types";
import type { LocationOption } from "../../api/types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { DescriptionList } from "../../components/DescriptionList";
import { FilterBar, FilterSelect } from "../../components/FilterBar";
import { Pagination } from "../../components/Pagination";
import { Tabs } from "../../components/Tabs";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { useQueryState, type QueryState } from "../../lib/query";

const TABS = [
  { id: "profile", label: "Business profile" },
  { id: "team", label: "Team" },
  { id: "activity", label: "Activity" },
];
type TabId = "profile" | "team" | "activity";

export function SettingsPage() {
  const query = useQueryState();
  const raw = query.get("tab", "profile");
  const tab: TabId = raw === "team" || raw === "activity" ? raw : "profile";
  return (
    <>
      <PageHeader title="Settings" subtitle="How this business is set up, who can sign in, and who did what. Seeded accounts only; nothing here can be edited." />
      <Tabs tabs={TABS} active={tab} label="Settings sections" onChange={(id) => query.set({ tab: id === "profile" ? null : id, kind: null })} />
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "profile" ? <ProfileTab /> : tab === "team" ? <TeamTab /> : <ActivityTab query={query} />}
      </div>
    </>
  );
}

function ProfileTab() {
  const profile = useApi<BusinessProfile>("/api/settings/profile");
  if (profile.error) return <LoadError error={profile.error} onRetry={profile.reload} />;
  if (!profile.data) return <LoadingState rows={6} />;
  const p = profile.data;
  const locationColumns: Column<LocationOption>[] = [
    { key: "name", header: "Location", render: (l) => l.name },
    { key: "address", header: "Address", render: (l) => `${l.address_line}, ${l.city}, ${l.state}` },
    { key: "id", header: "Id", render: (l) => <span className="mono">{l.id}</span> },
  ];
  return (
    <>
      <section className="card detail-summary" aria-label="Business profile">
        <DescriptionList
          columns={3}
          items={[
            { term: "Business name", value: p.name },
            { term: "Legal name", value: p.legal_name },
            { term: "Industry", value: p.industry },
            { term: "Support email", value: p.support_email },
            { term: "Reporting timezone", value: p.timezone },
            { term: "Payout schedule", value: p.payout_schedule_label },
            { term: "Payout destination", value: p.destination },
            { term: "On FinTechCo since", value: <Timestamp iso={p.created_at} mode="full" /> },
            { term: "Business id", value: <span className="mono">{p.id}</span> },
          ]}
        />
      </section>
      <section aria-labelledby="locations-heading">
        <h2 id="locations-heading" className="section-title">
          Locations
        </h2>
        {p.locations.length === 0 ? (
          <EmptyState title="No in-store locations" body="This business sells online only." />
        ) : (
          <DataTable caption="Locations" columns={locationColumns} rows={p.locations} rowKey={(l) => l.id} />
        )}
      </section>
    </>
  );
}

function TeamTab() {
  const team = useApi<TeamResponse>("/api/settings/team");
  if (team.error) return <LoadError error={team.error} onRetry={team.reload} />;
  if (!team.data) return <LoadingState rows={4} />;
  const columns: Column<TeamMember>[] = [
    { key: "name", header: "Name", render: (m) => m.user.full_name },
    { key: "title", header: "Title", render: (m) => m.title },
    { key: "email", header: "Email", render: (m) => m.email },
    { key: "role", header: "Role", render: (m) => m.role_label },
    {
      key: "status",
      header: "Status",
      render: (m) => (
        <span className={`badge ${m.is_active ? "badge-success" : "badge-neutral"}`}>
          <span className="badge-dot" aria-hidden="true" />
          {m.is_active ? "Active" : "Inactive"}
        </span>
      ),
    },
    { key: "since", header: "Member since", render: (m) => <Timestamp iso={m.member_since} /> },
  ];
  return (
    <>
      <p className="muted list-period">Seeded accounts only. Invitations and password recovery are not part of this portal.</p>
      <DataTable caption="Team members" columns={columns} rows={team.data.members} rowKey={(m) => m.membership_id} />
    </>
  );
}

const KIND_OPTIONS = [
  { value: "note", label: "Notes" },
  { value: "export", label: "CSV exports" },
];

function ActivityTab({ query }: { query: QueryState }) {
  const params = { kind: query.get("kind") || undefined, page: query.getInt("page", 1), page_size: 25 };
  const activity = useApi<ActivityResponse>(`/api/settings/activity${queryString(params)}`);
  const columns: Column<ActivityItem>[] = [
    { key: "when", header: "When", render: (a) => <Timestamp iso={a.created_at} /> },
    { key: "who", header: "Who", render: (a) => a.actor.full_name },
    { key: "what", header: "What", render: (a) => a.kind_label },
    { key: "subject", header: "Subject", render: (a) => <SubjectLink item={a} /> },
    { key: "details", header: "Details", render: (a) => <span className="activity-body">{a.body}</span> },
  ];
  return (
    <>
      <FilterBar>
        <FilterSelect id="activity-kind" label="Kind" value={query.get("kind")} options={KIND_OPTIONS} onChange={(v) => query.set({ kind: v })} />
      </FilterBar>
      {activity.error ? <LoadError error={activity.error} onRetry={activity.reload} /> : null}
      {!activity.error && !activity.data && activity.loading ? <LoadingState rows={6} /> : null}
      {activity.data && activity.data.items.length === 0 ? <EmptyState title="No activity yet" body="Notes and CSV downloads appear here with who did them and when." /> : null}
      {activity.data && activity.data.items.length > 0 ? (
        <>
          <DataTable caption="Activity" columns={columns} rows={activity.data.items} rowKey={(a) => a.id} loading={activity.loading} />
          <Pagination page={activity.data.page} pageSize={activity.data.page_size} total={activity.data.total} onPage={(p) => query.set({ page: p })} />
        </>
      ) : null}
    </>
  );
}

function SubjectLink({ item }: { item: ActivityItem }) {
  const s = item.subject;
  if (s.kind === "payment" && s.id) return <Link to={`/payments/${s.id}`} className="mono">{s.label}</Link>;
  if (s.kind === "dispute" && s.id) return <Link to={`/disputes/${s.id}`}>{s.label}</Link>;
  if (s.kind === "payout" && s.id) return <Link to={`/payouts/${s.id}`} className="mono">{s.label}</Link>;
  return <span className="mono">{s.label}</span>;
}
