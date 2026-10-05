import type { ReactNode } from "react";
import { SideNav } from "./SideNav";
import { TopBar } from "./TopBar";

export function AppShell({ merchantName, children }: { merchantName: string; children: ReactNode }) {
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <SideNav />
      <div className="shell-body">
        <TopBar merchantName={merchantName} />
        <main id="main" className="main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
