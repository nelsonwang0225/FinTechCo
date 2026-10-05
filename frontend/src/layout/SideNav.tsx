import { NavLink } from "react-router-dom";

export const NAV_ITEMS = [
  { to: "/overview", label: "Overview" },
  { to: "/payments", label: "Payments" },
  { to: "/payouts", label: "Payouts" },
  { to: "/customers", label: "Customers" },
  { to: "/disputes", label: "Disputes" },
  { to: "/reports", label: "Reports" },
  { to: "/settings", label: "Settings" },
] as const;

export function SideNav({ visible }: { visible?: ReadonlySet<string> }) {
  const items = visible ? NAV_ITEMS.filter((item) => visible.has(item.to)) : NAV_ITEMS;
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
