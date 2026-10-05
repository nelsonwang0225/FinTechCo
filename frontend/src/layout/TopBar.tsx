import type { ReactNode } from "react";
import { DemoIndicator } from "./DemoIndicator";

export function TopBar({ merchantName, right }: { merchantName: string; right?: ReactNode }) {
  return (
    <header className="topbar">
      <div className="topbar-merchant">
        <span className="topbar-label">Workspace</span>
        <span className="topbar-merchant-name">{merchantName}</span>
      </div>
      <div className="topbar-right">
        <DemoIndicator />
        {right}
      </div>
    </header>
  );
}
