"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { CourseRole, RosterEntryOut } from "@/lib/lms/types";
import { fmtApiDate } from "@/lib/format";
import { Badge, type BadgeTone, type PaginationProps, Table, buttonClasses, cn } from "@/components/ui";
import { fieldBase } from "@/components/ui/utils";

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
      columns={[
        {
          key: "name", header: t("courses.people.name"), primary: true,
          cell: (e) => (
            <span className="inline-flex flex-wrap items-center gap-2">
              <span className="break-words">{name(e)}</span>
              {e.is_owner && <Badge tone="info">{t("courses.roles.owner")}</Badge>}
            </span>
          ),
        },
        { key: "email", header: t("courses.people.email"), cell: (e) => <span className="break-all text-slate-700">{e.user.email}</span>, mobilePriority: 0 },
        {
          key: "role", header: t("courses.people.role"), mobilePriority: 1,
          cell: (e) => canChangeRole(e) ? (
            <select aria-label={`${t("courses.people.changeRole")}: ${name(e)}`} value={e.role} disabled={busyId === e.enrollment_id}
              onChange={(ev) => onChangeRole(e, ev.target.value as CourseRole)}
              className={cn(fieldBase, "min-h-11 w-auto border-slate-300 py-1.5 pr-8 sm:min-h-9")}>
              {roleOptions(e).map((r) => (
                <option key={r} value={r}>{t(`courses.roles.${r}`)}</option>
              ))}
            </select>
          ) : (
            <Badge tone={ROLE_TONE[e.role] ?? "neutral"}>{t(`courses.roles.${e.role}`)}</Badge>
          ),
        },
        {
          key: "state", header: t("courses.people.state"), mobilePriority: 2,
          cell: (e) => e.state === "removed"
            ? <Badge tone="neutral">{t("courses.people.states.removed")}</Badge>
            : <Badge tone="success">{t("courses.people.states.active")}</Badge>,
        },
        { key: "since", header: t("courses.people.since"), nowrap: true, mobilePriority: 3, cell: (e) => fmt(e.state === "removed" ? e.removed_at : e.activated_at) },
        // The actions column only when some row can be removed (no empty action rows in the phone cards).
        ...(entries.some(canRemove) ? [{
          key: "actions", header: "", actions: true, align: "right" as const,
          cell: (e: RosterEntryOut) => canRemove(e) ? (
            <button type="button" disabled={busyId === e.enrollment_id} onClick={() => onRemove(e)}
              className={buttonClasses({ variant: "secondary", size: "sm", className: "border-danger-200 text-danger-700 hover:bg-danger-50" })}>
              {t("courses.people.remove")}<span className="sr-only">: {name(e)}</span>
            </button>
          ) : e.is_owner ? <span className="whitespace-normal text-sm text-slate-600">{t("teaching.ownerStays")}</span> : null,
        }] : []),
      ]}
    />
  );
}
