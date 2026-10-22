"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { CourseRole, RosterEntryOut } from "@/lib/lms/types";

/**
 * Staff roster table. Action visibility is decided by the caller through the can* props
 * (owner-only actions per P1-8); the server enforces the real rules.
 */
export function RosterTable({
  entries,
  canRemove,
  canChangeRole,
  roleOptions,
  onChangeRole,
  onRemove,
  busyId,
}: {
  entries: RosterEntryOut[];
  canRemove: (e: RosterEntryOut) => boolean;
  canChangeRole: (e: RosterEntryOut) => boolean;
  roleOptions: (e: RosterEntryOut) => CourseRole[];
  onChangeRole: (e: RosterEntryOut, role: CourseRole) => void;
  onRemove: (e: RosterEntryOut) => void;
  busyId?: string | null;
}) {
  const { t } = useTranslation();
  const fmt = (s: string | null) => (s ? new Date(s).toLocaleDateString() : "—");
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{t("courses.people.tableCaption")}</caption>
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="px-4 py-3">{t("courses.people.name")}</th>
            <th scope="col" className="px-4 py-3">{t("courses.people.email")}</th>
            <th scope="col" className="px-4 py-3">{t("courses.people.role")}</th>
            <th scope="col" className="px-4 py-3">{t("courses.people.state")}</th>
            <th scope="col" className="px-4 py-3">{t("courses.people.since")}</th>
            <th scope="col" className="px-4 py-3"><span className="sr-only">{t("courses.people.actions")}</span></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {entries.map((e) => {
            const busy = busyId === e.enrollment_id;
            return (
              <tr key={e.enrollment_id}>
                <td className="px-4 py-3 font-medium text-slate-900">
                  {e.user.display_name || e.user.email.split("@")[0]}
                  {e.is_owner && <span className="ml-2 rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-700">{t("courses.roles.owner")}</span>}
                </td>
                <td className="px-4 py-3 text-slate-600">{e.user.email}</td>
                <td className="px-4 py-3">
                  {canChangeRole(e) ? (
                    <select aria-label={t("courses.people.changeRole")} value={e.role} disabled={busy}
                      onChange={(ev) => onChangeRole(e, ev.target.value as CourseRole)}
                      className="rounded-lg border border-slate-300 px-2 py-1 text-sm">
                      {roleOptions(e).map((r) => (
                        <option key={r} value={r}>{t(`courses.roles.${r}`)}</option>
                      ))}
                    </select>
                  ) : (
                    t(`courses.roles.${e.role}`)
                  )}
                </td>
                <td className="px-4 py-3 text-slate-600">{t(`courses.people.states.${e.state === "removed" ? "removed" : "active"}`)}</td>
                <td className="px-4 py-3 text-slate-600">{fmt(e.state === "removed" ? e.removed_at : e.activated_at)}</td>
                <td className="px-4 py-3 text-right">
                  {canRemove(e) && (
                    <button type="button" disabled={busy} onClick={() => onRemove(e)}
                      className="text-sm font-semibold text-red-600 hover:underline disabled:opacity-50">
                      {t("courses.people.remove")}
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
