import { NavLink } from "react-router-dom";
import type { Permission } from "../api/types";

export interface NavItem {
  to: string;
  label: string;
  /** Any one of these permissions shows the item. The backend enforces regardless. */
  anyOf: Permission[];
}

export const NAV_ITEMS: readonly NavItem[] = [
  { to: "/overview", label: "Overview", anyOf: ["overview:read"] },
  { to: "/payments", label: "Payments", anyOf: ["payments:read"] },
  { to: "/payouts", label: "Payouts", anyOf: ["payouts:read"] },
  { to: "/customers", label: "Customers", anyOf: ["customers:read"] },
  { to: "/disputes", label: "Disputes", anyOf: ["disputes:read"] },
  { to: "/reports", label: "Reports", anyOf: ["reports:operational", "reports:financial"] },
  { to: "/settings", label: "Settings", anyOf: ["settings:read"] },
];

export function SideNav({ can }: { can: (permission: Permission) => boolean }) {
  const items = NAV_ITEMS.filter((item) => item.anyOf.some(can));
  return (
    <nav className="sidenav" aria-label="Sections">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true" />
        <span className="brand-name">FinTechCo</span>
        <span className="brand-product">Business</span>
      </div>
      <ul className="nav-list">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink to={item.to} className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
