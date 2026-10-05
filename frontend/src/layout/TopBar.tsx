import type { Session } from "../api/types";
import { DemoIndicator } from "./DemoIndicator";

export function TopBar({ session }: { session: Session }) {
  return (
    <header className="topbar">
      <div className="topbar-merchant">
        <span className="topbar-label">Business</span>
        <span className="topbar-merchant-name">{session.merchant.name}</span>
      </div>
      <div className="topbar-right">
        <DemoIndicator />
        <span className="topbar-user">
          <span className="topbar-user-name">{session.user.full_name}</span>
          <span className="topbar-user-role">{session.role_label}</span>
        </span>
      </div>
    </header>
  );
}
