"use client";

import React from "react";
import { Building2, FolderTree } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { DepartmentOut } from "@/lib/lms/organizations";
import { MenuButton, cn } from "@/components/ui";
import { OrgBadge } from "./OrgUi";

export type DepartmentAction = "create" | "rename" | "move" | "delete" | "suspend" | "resume";

/**
 * Phase 9 S2 (PHASE_9_DESIGN 8.1, 8.4): the subtree of an organization as an indented list (one level of indent
 * per depth, so it stays readable at 375 px). Each row has one "⋯" menu; the first row is the organization of the
 * page (no rename / move / delete here). `readOnly` hides the menus (suspended organization). `mode="platform"`
 * (platform admin's Departments tab) offers only Suspend / Resume on the departments (the organization itself is
 * suspended from the page header).
 */
export function DepartmentTree({ rows, readOnly = false, onAction, mode = "org" }: {
  rows: DepartmentOut[];
  readOnly?: boolean;
  onAction?: (action: DepartmentAction, dept: DepartmentOut) => void;
  mode?: "org" | "platform";
}) {
  const { t } = useTranslation();
  if (rows.length === 0) return null;
  const top = rows[0].depth;
  return (
    <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
      {rows.map((d, i) => {
        const level = d.depth - top;
        const isTop = i === 0;
        const items = mode === "platform" ? (isTop ? [] : [d.status === "suspended"
          ? { id: "resume", label: t("organizations.admin.resume") }
          : { id: "suspend", label: t("organizations.admin.suspend") }]) : [
          ...(d.depth < 2 ? [{ id: "create", label: t("departments.create") }] : []),
          ...(isTop ? [] : [
            { id: "rename", label: t("departments.rename") },
            { id: "move", label: t("departments.move") },
            { id: "delete", label: t("departments.delete") },
          ]),
        ];
        return (
          <li key={d.id} className="flex items-start gap-3 px-4 py-3 sm:px-6">
            <div className={cn("flex min-w-0 flex-1 items-start gap-3", level === 1 && "pl-4 sm:pl-6", level >= 2 && "pl-8 sm:pl-12")}>
              {isTop
                ? <Building2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-slate-500" />
                : <FolderTree aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-slate-500" />}
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2 break-words font-semibold text-slate-900">
                  <span className="min-w-0 break-words">{d.name}</span>
                  {d.status === "suspended" && <OrgBadge tone="suspended" labelKey="organizations.status.suspended" />}
                </p>
                <p className="mt-0.5 text-sm text-slate-600">
                  {isTop && top === 0 ? `${t("departments.whole")} · ` : ""}
                  {t("departments.counts", { courses: d.courses, members: d.members })}
                </p>
              </div>
            </div>
            {!readOnly && onAction && items.length > 0 && (
              <MenuButton label={<span aria-label={t("departments.actions", { name: d.name })}>⋯</span>} variant="secondary" size="sm"
                items={items} onSelect={(id) => onAction(id as DepartmentAction, d)} />
            )}
          </li>
        );
      })}
    </ul>
  );
}
