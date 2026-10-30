"use client";

// Phase 9 S3 (PHASE_9_DESIGN 8.1, 8.2): Course → People as tabs Roster · Invitations · Applications (staff only).
// The Applications slot belongs to S4 (`ApplicationsInbox`); it is shown only when the page passes `showApplications`
// (form enrollment modes, or applications exist). Students never see the tabs.
import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { TabPanel, Tabs } from "@/components/ui";

export type PeopleTab = "roster" | "invitations" | "applications";

export const PEOPLE_TABS_ID = "people-tabs";

export function PeopleTabs({
  value, onChange, roster, invitations, applications, showInvitations = true, showApplications = false,
  invitationsCount, applicationsCount,
}: {
  value: PeopleTab;
  onChange: (tab: PeopleTab) => void;
  roster: React.ReactNode;
  invitations: React.ReactNode;
  /** S4's applications inbox (slot `applications`); nothing is rendered while it is absent. */
  applications?: React.ReactNode;
  showInvitations?: boolean;
  showApplications?: boolean;
  invitationsCount?: number | null;
  applicationsCount?: number | null;
}) {
  const { t } = useTranslation();
  const withApplications = showApplications && applications !== undefined && applications !== null;
  const items = [
    { id: "roster", label: t("studentInvite.tabs.roster") },
    ...(showInvitations ? [{ id: "invitations", label: t("studentInvite.tabs.invitations"), count: invitationsCount || undefined }] : []),
    ...(withApplications ? [{ id: "applications", label: t("studentInvite.tabs.applications"), count: applicationsCount || undefined }] : []),
  ];
  const current: PeopleTab = items.some((i) => i.id === value) ? value : "roster";
  if (items.length === 1) return <>{roster}</>; // e.g. assistants: no invitations, no applications -> no tab row
  return (
    <div>
      <Tabs id={PEOPLE_TABS_ID} label={t("studentInvite.tabs.label")} items={items} value={current}
        onChange={(id) => onChange(id as PeopleTab)} />
      <TabPanel tabsId={PEOPLE_TABS_ID} value={current}>
        {current === "roster" ? roster : current === "invitations" ? invitations : applications}
      </TabPanel>
    </div>
  );
}
