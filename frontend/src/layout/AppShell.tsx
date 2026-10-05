import type { ReactNode } from "react";
import { useSession } from "../session/SessionProvider";
import { SideNav } from "./SideNav";
import { TopBar } from "./TopBar";

export function AppShell({ children }: { children: ReactNode }) {
  const { session, can } = useSession();
  if (!session) return null;
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <SideNav can={can} />
      <div className="shell-body">
        <TopBar session={session} />
        <main id="main" className="main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
