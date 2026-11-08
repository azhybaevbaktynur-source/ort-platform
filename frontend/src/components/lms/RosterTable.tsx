"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { CourseRole, RosterEntryOut } from "@/lib/lms/types";
import { fmtApiDate } from "@/lib/format";
import { Badge, type BadgeTone, type PaginationProps, Table } from "@/components/ui";
import { OutlineMenu } from "@/components/lms/modules/OutlineMenu";

const ROLE_TONE: Record<string, BadgeTone> = { teacher: "info", assistant: "neutral", student: "neutral" };

/**
 * Staff roster table. Action visibility is decided by the caller through the can* props
 * (owner-only actions per P1-8); the server enforces the real rules.
 * Phase 6b S5c (UX T2): design-system Table: stacked cards under 640 px (name + role, email, actions row), a count line.
 */
export function RosterTable({
  entries,
  canRemove,
  canChangeRole,
  roleOptions,
  onChangeRole,
  onRemove,
  busyId,
  countText,
  pagination,
}: {
  entries: RosterEntryOut[];
  canRemove: (e: RosterEntryOut) => boolean;
  canChangeRole: (e: RosterEntryOut) => boolean;
  roleOptions: (e: RosterEntryOut) => CourseRole[];
  onChangeRole: (e: RosterEntryOut, role: CourseRole) => void;
  onRemove: (e: RosterEntryOut) => void;
  busyId?: string | null;
  countText?: string;
  pagination?: PaginationProps;
}) {
  const { t } = useTranslation();
  const fmt = (s: string | null) => fmtApiDate(s) || "—";
  const name = (e: RosterEntryOut) => e.user.display_name || e.user.email.split("@")[0];
  return (
    <Table<RosterEntryOut>
      caption={t("courses.people.tableCaption")}
      rows={entries}
      rowKey={(e) => e.enrollment_id}
      countText={countText}
      pagination={pagination}
      density="compact"
      columns={[
        {
          key: "name", header: t("courses.people.name"), primary: true,
          cell: (e) => (
            <span className="inline-flex flex-wrap items-center gap-2">
              <span className="break-words">{name(e)}</span>
              {e.is_owner && <Badge tone="info" title={t("teaching.ownerStays")}>{t("courses.roles.owner")}</Badge>}
            </span>
          ),
        },
        { key: "email", header: t("courses.people.email"), cell: (e) => <span className="break-all text-slate-700">{e.user.email}</span>, mobilePriority: 0 },
        {
          key: "role", header: t("courses.people.role"), mobilePriority: 1,
          cell: (e) => <Badge tone={ROLE_TONE[e.role] ?? "neutral"}>{t(`courses.roles.${e.role}`)}</Badge>,
        },
        {
          key: "state", header: t("courses.people.state"), mobilePriority: 2,
          cell: (e) => e.state === "removed"
            ? <Badge tone="neutral">{t("courses.people.states.removed")}</Badge>
            : <Badge tone="success">{t("courses.people.states.active")}</Badge>,
        },
        { key: "since", header: t("courses.people.since"), nowrap: true, mobilePriority: 3, cell: (e) => fmt(e.state === "removed" ? e.removed_at : e.activated_at) },
        // The actions column only when some row can be removed (no empty action rows in the phone cards).
        ...(entries.some((e) => canRemove(e) || canChangeRole(e)) ? [{
          key: "actions", header: "", actions: true, align: "right" as const,
          cell: (e: RosterEntryOut) => {
            const roleItems = canChangeRole(e)
              ? roleOptions(e).filter((r) => r !== e.role).map((r) => ({ id: `role:${r}`, label: `${t("courses.people.changeRole")}: ${t(`courses.roles.${r}`)}` }))
              : [];
            const groups = [
              ...(roleItems.length ? [{ id: "role", items: roleItems }] : []),
              ...(canRemove(e) ? [{ id: "person", items: [{ id: "remove", label: t("courses.people.remove"), danger: true }] }] : []),
            ];
            if (!groups.length) return null;
            return (
              <OutlineMenu className="sm:-my-2" label={t("modules.editor.actionsFor", { title: name(e) })} disabled={busyId === e.enrollment_id}
                groups={groups}
                onSelect={(id) => (id === "remove" ? onRemove(e) : onChangeRole(e, id.slice(5) as CourseRole))} />
            );
          },
        }] : []),
      ]}
    />
  );
}
