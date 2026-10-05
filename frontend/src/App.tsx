import { Navigate, Route, Routes } from "react-router-dom";
import type { Session } from "./api/types";
import { PersonaBar } from "./dev/PersonaBar";
import { PersonaChooser } from "./dev/PersonaChooser";
import { AppShell } from "./layout/AppShell";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OverviewPage } from "./pages/overview/OverviewPage";
import { PagePlaceholder } from "./pages/PagePlaceholder";
import { PaymentDetailPage } from "./pages/payment-detail/PaymentDetailPage";
import { PaymentsPage } from "./pages/payments/PaymentsPage";
import { PayoutDetailPage } from "./pages/payout-detail/PayoutDetailPage";
import { PayoutsPage } from "./pages/payouts/PayoutsPage";
import { RequirePermission } from "./session/RequirePermission";
import { SessionProvider, useSession } from "./session/SessionProvider";

export function App() {
  return (
    <SessionProvider>
      <Root />
    </SessionProvider>
  );
}

function Root() {
  const { status, session } = useSession();
  if (status === "loading") {
    return (
      <div className="boot" role="status" aria-live="polite">
        Loading FinTechCo Business…
      </div>
    );
  }
  if (status === "anonymous" || !session) {
    return <PersonaChooser />;
  }
  // Keyed by membership so switching persona remounts the whole product and nothing from the previous business stays on screen.
  return (
    <div className="dev-frame">
      <PersonaBar />
      <ProductApp key={session.membership_id} session={session} />
    </div>
  );
}

function ProductApp(_: { session: Session }) {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/overview" replace />} />
        <Route
          path="/overview"
          element={
            <RequirePermission permission="overview:read">
              <OverviewPage />
            </RequirePermission>
          }
        />
        <Route
          path="/payments"
          element={
            <RequirePermission permission="payments:read">
              <PaymentsPage />
            </RequirePermission>
          }
        />
        <Route
          path="/payments/:paymentId"
          element={
            <RequirePermission permission="payments:read">
              <PaymentDetailPage />
            </RequirePermission>
          }
        />
        <Route
          path="/payouts"
          element={
            <RequirePermission permission="payouts:read">
              <PayoutsPage />
            </RequirePermission>
          }
        />
        <Route
          path="/payouts/:payoutId"
          element={
            <RequirePermission permission="payouts:read">
              <PayoutDetailPage />
            </RequirePermission>
          }
        />
        <Route
          path="/customers/*"
          element={
            <RequirePermission permission="customers:read">
              <PagePlaceholder title="Customers" />
            </RequirePermission>
          }
        />
        <Route
          path="/disputes/*"
          element={
            <RequirePermission permission="disputes:read">
              <PagePlaceholder title="Disputes" />
            </RequirePermission>
          }
        />
        <Route path="/reports" element={<PagePlaceholder title="Reports" />} />
        <Route
          path="/settings/*"
          element={
            <RequirePermission permission="settings:read">
              <PagePlaceholder title="Settings" />
            </RequirePermission>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  );
}
