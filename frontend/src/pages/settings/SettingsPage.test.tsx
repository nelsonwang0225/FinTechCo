import { afterEach, describe, expect, it } from "vitest";
import type { ActivityResponse, BusinessProfile, TeamResponse } from "../../api/settings-types";
import { JORDAN, mockFetch, type Handler } from "../../test/mockApi";
import { click, flush, renderPage, type Rendered } from "../../test/render";
import { SettingsPage } from "./SettingsPage";

let page: Rendered | null = null;

afterEach(() => {
  page?.unmount();
  page = null;
});

const PROFILE: BusinessProfile = {
  id: "mer_alderloom00001",
  name: "Alder & Loom",
  slug: "alder-loom",
  legal_name: "Alder & Loom Home LLC",
  support_email: "support@alder-loom.example.com",
  industry: "Homeware retail",
  timezone: "America/Chicago",
  payout_schedule: "daily",
  payout_schedule_label: "Every business day",
  destination: "Alder & Loom, Operating account •••• 4821, external bank account, demo record",
  destination_label: "Operating account",
  destination_last4: "4821",
  destination_kind: "external bank account",
  created_at: "2025-08-01T05:00:00Z",
  locations: [{ id: "loc_fultonmarket01", name: "Fulton Market", address_line: "815 W Fulton Market", city: "Chicago", state: "IL" }],
};
const TEAM: TeamResponse = {
  members: [
    { membership_id: "mem_jordan00000001", user: { id: "usr_jordan00000001", full_name: "Jordan Ellis" }, email: "jordan.ellis@alder-loom.example.com", title: "Business Administrator", role: "business_admin", role_label: "Business admin", is_active: true, member_since: "2025-08-01T05:00:00Z" },
    { membership_id: "mem_maya0000000001", user: { id: "usr_maya0000000001", full_name: "Maya Chen" }, email: "maya.chen@alder-loom.example.com", title: "Operations Manager", role: "operations_manager", role_label: "Operations manager", is_active: true, member_since: "2025-08-01T05:00:00Z" },
  ],
};
const ACTIVITY: ActivityResponse = {
  items: [
    { id: "evt_1", kind: "export", kind_label: "CSV exported", actor: { id: "usr_daniel00000001", full_name: "Daniel Brooks" }, subject: { kind: "export", id: null, label: "alder-loom_refunds_2026-09-29_2026-10-05.csv" }, body: "Downloaded the refund register CSV for last 7 days (Sep 29 – Oct 5, 2026).", created_at: "2026-10-05T15:00:00Z" },
    { id: "evt_2", kind: "note", kind_label: "Note added", actor: { id: "usr_maya0000000001", full_name: "Maya Chen" }, subject: { kind: "dispute", id: "dp_open0000000001", label: "Dispute on AL-10831" }, body: "Asked the carrier for proof of delivery.", created_at: "2026-09-24T15:00:00Z" },
    { id: "evt_3", kind: "note", kind_label: "Note added", actor: { id: "usr_maya0000000001", full_name: "Maya Chen" }, subject: { kind: "payment", id: "pay_anchor00000001", label: "AL-11404" }, body: "Shopper confirmed the duvet arrived.", created_at: "2026-09-23T15:00:00Z" },
  ],
  page: 1,
  page_size: 25,
  total: 3,
};

const handler: Handler = (url) => {
  if (url === "/api/session") return { status: 200, body: JORDAN };
  if (url === "/api/settings/profile") return { status: 200, body: PROFILE };
  if (url === "/api/settings/team") return { status: 200, body: TEAM };
  if (url.startsWith("/api/settings/activity")) return { status: 200, body: ACTIVITY };
  return undefined;
};

describe("SettingsPage", () => {
  it("opens on the business profile with the masked destination and locations", async () => {
    mockFetch(handler);
    page = await renderPage(<SettingsPage />, "/settings");
    await flush();
    const text = page.container.textContent ?? "";
    expect(text).toContain("Alder & Loom Home LLC");
    expect(text).toContain("America/Chicago");
    expect(text).toContain("Every business day");
    expect(text).toContain("Operating account •••• 4821");
    expect(text).toContain("Fulton Market");
    expect(page.container.querySelectorAll("button, input, select").length).toBe(3); // the three tabs; nothing is editable
  });

  it("switches to the team and activity tabs through the URL", async () => {
    const { calls } = mockFetch(handler);
    page = await renderPage(<SettingsPage />, "/settings");
    await flush();
    const el = page.container;
    const tab = (label: string) => Array.from(el.querySelectorAll("[role=tab]")).find((t) => t.textContent === label) ?? null;
    await click(tab("Team"));
    await flush();
    expect(calls.some((c) => c.url === "/api/settings/team")).toBe(true);
    expect(el.textContent).toContain("Operations manager");
    expect(el.textContent).toContain("Seeded accounts only");
    await click(tab("Activity"));
    await flush();
    expect(calls.some((c) => c.url.startsWith("/api/settings/activity"))).toBe(true);
    const rows = el.querySelectorAll("tbody tr");
    expect(rows.length).toBe(3);
    expect(rows[0]?.textContent).toContain("Daniel Brooks");
    expect(rows[0]?.textContent).toContain("CSV exported");
    expect(rows[1]?.querySelector("a")?.getAttribute("href")).toBe("/disputes/dp_open0000000001");
    expect(rows[2]?.querySelector("a")?.getAttribute("href")).toBe("/payments/pay_anchor00000001");
  });
});
