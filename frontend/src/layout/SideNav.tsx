import type { ComponentType, SVGProps } from "react";
import { NavLink } from "react-router-dom";
import type { Permission } from "../api/types";
import { DemoIndicator } from "./DemoIndicator";
import { IconCustomers, IconDisputes, IconOverview, IconPaymentHealth, IconPayments, IconPayouts, IconReports, IconSettings } from "./icons";

export interface NavItem {
  to: string;
  label: string;
  /** Any one of these permissions shows the item. The backend enforces regardless. */
  anyOf: Permission[];
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { to: "/overview", label: "Overview", anyOf: ["overview:read"], icon: IconOverview },
  { to: "/payments", label: "Payments", anyOf: ["payments:read"], icon: IconPayments },
  { to: "/payment-health", label: "Payment Health", anyOf: ["payments:read"], icon: IconPaymentHealth },
  { to: "/payouts", label: "Payouts", anyOf: ["payouts:read"], icon: IconPayouts },
  { to: "/customers", label: "Customers", anyOf: ["customers:read"], icon: IconCustomers },
  { to: "/disputes", label: "Disputes", anyOf: ["disputes:read"], icon: IconDisputes },
  { to: "/reports", label: "Reports", anyOf: ["reports:operational", "reports:financial"], icon: IconReports },
  { to: "/settings", label: "Settings", anyOf: ["settings:read"], icon: IconSettings },
];

export function SideNav({ can }: { can: (permission: Permission) => boolean }) {
  const items = NAV_ITEMS.filter((item) => item.anyOf.some(can));
  return (
    <nav className="sidenav" aria-label="Sections">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true" />
        <span className="brand-text">
          <span className="brand-name">FinTechCo</span>
          <span className="brand-product">Business</span>
        </span>
      </div>
      <ul className="nav-list">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <li key={item.to}>
              <NavLink to={item.to} className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
                <Icon />
                <span>{item.label}</span>
              </NavLink>
            </li>
          );
        })}
      </ul>
      <div className="sidenav-foot">
        <DemoIndicator />
      </div>
    </nav>
  );
}
