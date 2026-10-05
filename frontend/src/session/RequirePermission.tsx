import type { ReactNode } from "react";
import type { Permission } from "../api/types";
import { ForbiddenState } from "../components/states";
import { useSession } from "./SessionProvider";

/** Renders children only when the role holds the permission; otherwise the forbidden state. The backend enforces. */
export function RequirePermission({ permission, children }: { permission: Permission; children: ReactNode }) {
  const { can } = useSession();
  if (!can(permission)) {
    return <ForbiddenState />;
  }
  return <>{children}</>;
}
