"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { AuditEntryOut } from "@/lib/lms/types";
import { fmtApiDateTime } from "@/lib/format";

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
  const details = (e: AuditEntryOut) => (e.details && Object.keys(e.details).length ? JSON.stringify(e.details) : "—");
  return (
    <>
    {/* Phase 6 S8 (UX P1): phones get stacked cards (when, who, action, reason); object and details behind a tap. */}
    <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white md:hidden">
      {entries.map((e) => (
        <li key={e.id} className="min-w-0 px-4 py-3 text-sm">
          <p className="break-words text-xs text-slate-500">{fmtApiDateTime(e.created_at, lang)} · {e.actor.display_name || e.actor.email}</p>
          <p className="mt-1 break-words font-medium text-slate-900">{label(e.action)}</p>
          {e.reason && <p className="mt-1 break-words text-slate-700"><span className="text-slate-500">{t("platformAdmin.audit.reason")}:</span> {e.reason}</p>}
          <details className="mt-1">
            <summary className="inline-flex min-h-[44px] cursor-pointer items-center text-sm font-medium text-brand-700">{t("platformAdmin.audit.details")}</summary>
            <p className="break-all text-xs"><span className="text-slate-500">{e.target_type}</span> <code>{e.target_id}</code></p>
            <code className="mt-1 block break-all text-xs text-slate-600">{details(e)}</code>
          </details>
        </li>
      ))}
    </ul>
    <div className="hidden overflow-x-auto rounded-2xl border border-slate-200 bg-white md:block">
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
              <td className="whitespace-nowrap px-3 py-2">{fmtApiDateTime(e.created_at, lang)}</td>
              <td className="px-3 py-2">{e.actor.display_name || e.actor.email}</td>
              <td className="px-3 py-2 font-medium">{label(e.action)}</td>
              <td className="px-3 py-2"><span className="text-slate-500">{e.target_type}</span> <code className="text-xs">{e.target_id}</code></td>
              <td className="px-3 py-2">{e.reason || "—"}</td>
              <td className="px-3 py-2"><code className="break-all text-xs text-slate-600">{details(e)}</code></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    </>
  );
}
