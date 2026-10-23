"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { AuditEntryOut } from "@/lib/lms/types";

export function useAuditActionLabel() {
  const { t } = useTranslation();
  return (action: string) => {
    const key = `platformAdmin.auditActions.${action.replace(/\./g, "_")}`;
    const label = t(key);
    return label === key ? action : label;
  };
}

export function AuditTable({ entries }: { entries: AuditEntryOut[] }) {
  const { t, lang } = useTranslation();
  const label = useAuditActionLabel();
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2">{t("platformAdmin.audit.when")}</th>
            <th className="px-3 py-2">{t("platformAdmin.audit.actor")}</th>
            <th className="px-3 py-2">{t("platformAdmin.audit.action")}</th>
            <th className="px-3 py-2">{t("platformAdmin.audit.target")}</th>
            <th className="px-3 py-2">{t("platformAdmin.audit.reason")}</th>
            <th className="px-3 py-2">{t("platformAdmin.audit.details")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {entries.map((e) => (
            <tr key={e.id} className="align-top">
              <td className="whitespace-nowrap px-3 py-2">{new Date(e.created_at).toLocaleString(lang)}</td>
              <td className="px-3 py-2">{e.actor.display_name || e.actor.email}</td>
              <td className="px-3 py-2 font-medium">{label(e.action)}</td>
              <td className="px-3 py-2"><span className="text-slate-500">{e.target_type}</span> <code className="text-xs">{e.target_id}</code></td>
              <td className="px-3 py-2">{e.reason || "—"}</td>
              <td className="px-3 py-2"><code className="break-all text-xs text-slate-600">{e.details && Object.keys(e.details).length ? JSON.stringify(e.details) : "—"}</code></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
