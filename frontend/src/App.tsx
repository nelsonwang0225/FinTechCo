import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { PagePlaceholder } from "./pages/PagePlaceholder";

export function App() {
  return (
    <AppShell merchantName="FinTechCo Business">
      <Routes>
        <Route path="/" element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<PagePlaceholder title="Overview" />} />
        <Route path="/payments" element={<PagePlaceholder title="Payments" />} />
        <Route path="/payouts" element={<PagePlaceholder title="Payouts" />} />
        <Route path="/customers" element={<PagePlaceholder title="Customers" />} />
        <Route path="/disputes" element={<PagePlaceholder title="Disputes" />} />
        <Route path="/reports" element={<PagePlaceholder title="Reports" />} />
        <Route path="/settings" element={<PagePlaceholder title="Settings" />} />
        <Route path="*" element={<PagePlaceholder title="Page not found" />} />
      </Routes>
    </AppShell>
  );
}
