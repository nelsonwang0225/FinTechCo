import type { Session } from "../api/types";
import { initials } from "../lib/format";

/** Who is signed in, where: the business on the left, the person and their role on the right. */
export function TopBar({ session }: { session: Session }) {
  return (
    <header className="topbar">
      <div className="topbar-merchant">
        <span className="topbar-label">Business</span>
        <span className="topbar-merchant-name">{session.merchant.name}</span>
      </div>
      <div className="topbar-right">
        <span className="topbar-user">
          <span className="topbar-avatar" aria-hidden="true">
            {initials(session.user.full_name)}
          </span>
          <span className="topbar-user-text">
            <span className="topbar-user-name">{session.user.full_name}</span>
            <span className="topbar-user-role">{session.role_label}</span>
          </span>
        </span>
      </div>
    </header>
  );
}
