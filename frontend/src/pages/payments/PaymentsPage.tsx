import { Link } from "react-router-dom";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Tabs } from "../../components/Tabs";
import { ErrorState, LoadingState } from "../../components/states";
import { IconChevronLeft } from "../../layout/icons";
import { PageHeader } from "../../layout/PageHeader";
import { useQueryState } from "../../lib/query";
import { backToHealthHref } from "../payment-health/links";
import { AttemptsTab } from "./AttemptsTab";
import { PaymentsTab } from "./PaymentsTab";

const TABS = [
  { id: "payments", label: "Payments" },
  { id: "attempts", label: "Attempts" },
];

export function PaymentsPage() {
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const tab = query.get("tab", "payments") === "attempts" ? "attempts" : "payments";
  const backToHealth = backToHealthHref(query);

  return (
    <>
      <PageHeader
        title="Payments"
        subtitle="Search and investigate payment activity across channels. Times are shown in America/Chicago."
        above={
          backToHealth ? (
            <Link to={backToHealth}>
              <IconChevronLeft />
              Back to Payment Health
            </Link>
          ) : undefined
        }
      />
      <Tabs
        tabs={TABS}
        active={tab}
        label="Payments views"
        onChange={(id) => query.set({ tab: id === "payments" ? null : id, status: null, outcome: null, failure_code: null, sort: null, dir: null })}
      />
      {meta.loading && !meta.data ? <LoadingState rows={4} /> : null}
      {meta.error ? <ErrorState error={meta.error} onRetry={meta.reload} /> : null}
      {meta.data ? (
        <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
          {tab === "payments" ? <PaymentsTab meta={meta.data} query={query} /> : <AttemptsTab meta={meta.data} query={query} />}
        </div>
      ) : null}
    </>
  );
}
