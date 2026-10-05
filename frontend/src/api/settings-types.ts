// Wire types for Settings: business profile, team and activity. All read-only.
import type { ListResponse, LocationOption } from "./types";

export interface BusinessProfile {
  id: string;
  name: string;
  slug: string;
  legal_name: string;
  support_email: string;
  industry: string;
  timezone: string;
  payout_schedule: string;
  payout_schedule_label: string;
  destination: string;
  destination_label: string;
  destination_last4: string;
  destination_kind: string;
  created_at: string;
  locations: LocationOption[];
}

export interface TeamMember {
  membership_id: string;
  user: { id: string; full_name: string };
  email: string;
  title: string;
  role: string;
  role_label: string;
  is_active: boolean;
  member_since: string;
}

export interface TeamResponse {
  members: TeamMember[];
}

export interface ActivitySubject {
  kind: "payment" | "dispute" | "payout" | "export";
  id: string | null;
  label: string;
}

export interface ActivityItem {
  id: string;
  kind: "note" | "export";
  kind_label: string;
  actor: { id: string; full_name: string };
  subject: ActivitySubject;
  body: string;
  created_at: string;
}

export type ActivityResponse = ListResponse<ActivityItem>;
