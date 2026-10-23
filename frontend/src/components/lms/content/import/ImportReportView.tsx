"use client";

import React from "react";
import Link from "next/link";
import { AlertCircle, AlertTriangle, CheckCircle2, ImageIcon } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { ImportBankSummary, ImportIssue, ImportReport } from "@/lib/lms/contentImport";
import { btnSecondary, cardCls } from "@/components/lms/content/ui";

const sum = (o: Record<string, number>) => Object.values(o).reduce((a, n) => a + n, 0);

export function ImportIssues({ issues, kind }: { issues: ImportIssue[]; kind: "error" | "warning" }) {
  const { t } = useTranslation();
  if (issues.length === 0) return null;
  const isError = kind === "error";
  const text = (issue: ImportIssue) => {
    const key = `bank.import.issues.${issue.code}`;
    const params = Object.fromEntries(
      Object.entries(issue.params || {}).map(([k, v]) => [k, Array.isArray(v) ? v.join(", ") : String(v ?? "")]),
    );
    const translated = t(key, params);
    // Missing translation or missing params: show the server text.
    return translated === key || /\{\w+\}/.test(translated) ? issue.message : translated;
  };
  return (
    <div className={`rounded-2xl border text-xs ${isError ? "border-rose-200 bg-rose-50 text-rose-900" : "border-amber-200 bg-amber-50 text-amber-900"}`}>
      <div role={isError ? "alert" : undefined} className="flex items-center gap-2 px-4 pt-3 font-bold">
        {isError ? <AlertCircle className="h-4 w-4" aria-hidden="true" /> : <AlertTriangle className="h-4 w-4" aria-hidden="true" />}
        {t(isError ? "bank.import.errorsHeading" : "bank.import.warningsHeading", { count: issues.length })}
      </div>
      <div className="max-h-72 overflow-auto px-4 pb-3 pt-2">
        <table className="w-full text-left">
          <thead>
            <tr className="opacity-70">
              <th className="whitespace-nowrap py-1 pr-3 font-semibold">{t("bank.import.row")}</th>
              <th className="whitespace-nowrap py-1 pr-3 font-semibold">{t("bank.import.column")}</th>
              <th className="whitespace-nowrap py-1 pr-3 font-semibold">{t("bank.import.file")}</th>
              <th className="py-1 font-semibold">{t("bank.import.message")}</th>
            </tr>
          </thead>
          <tbody>
            {issues.map((issue, idx) => (
              <tr key={idx} className="border-t border-black/5 align-top">
                <td className="py-1 pr-3 font-mono">{issue.row ?? "—"}</td>
                <td className="py-1 pr-3 font-mono">{issue.column ?? "—"}</td>
                <td className="break-all py-1 pr-3 font-mono">{issue.file ?? issue.bundle ?? "—"}</td>
                <td className="py-1">{text(issue)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BankSummary({ b, done, bankBase }: { b: ImportBankSummary; done: boolean; bankBase: string }) {
  const { t } = useTranslation();
  const sections = Object.keys(b.sections);
  const sectionName = (sec: string) => {
    const label = t(`sections.${sec}`);
    return label === `sections.${sec}` ? sec : label;
  };
  const cols: { key: "created" | "updated" | "unchanged" | "conflicts" | "skipped_deleted"; cls: string }[] = [
    { key: "created", cls: "text-emerald-700" },
    { key: "updated", cls: "text-indigo-700" },
    { key: "unchanged", cls: "text-slate-600" },
    { key: "conflicts", cls: "text-amber-700" },
    { key: "skipped_deleted", cls: "text-slate-500" },
  ];
  return (
    <div className={`${cardCls} space-y-3 bg-slate-50`}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-700">
        <span>
          <strong>{t("bank.import.source")}:</strong>{" "}
          <span className="font-mono">{b.source_id || t("bank.import.noManifest")}</span> ({b.language.toUpperCase()})
        </span>
        <span>
          <strong>{t("bank.import.folder")}:</strong> <span className="font-mono">{b.root || "/"}</span>
        </span>
        <span>
          <strong>{t("bank.import.bank")}:</strong> {b.bank_title}{" "}
          {!done && <span className="text-slate-500">({t(b.bank_exists ? "bank.import.bankExisting" : "bank.import.bankNew")})</span>}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="text-slate-500">
              <th className="py-1 pr-3 font-semibold">{t("bank.import.section")}</th>
              <th className="py-1 pr-3 text-right font-semibold">{t("bank.import.total")}</th>
              {cols.map((c) => (
                <th key={c.key} className="py-1 pr-3 text-right font-semibold">{t(`bank.import.col.${c.key}`)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sections.map((sec) => (
              <tr key={sec} className="border-t border-slate-200">
                <td className="py-1 pr-3 text-slate-800">{sectionName(sec)}</td>
                <td className="py-1 pr-3 text-right font-mono">{b.sections[sec]}</td>
                {cols.map((c) => (
                  <td key={c.key} className={`py-1 pr-3 text-right font-mono ${c.cls}`}>{b[c.key][sec] || 0}</td>
                ))}
              </tr>
            ))}
            <tr className="border-t border-slate-300 font-bold">
              <td className="py-1 pr-3">{t("bank.import.total")}</td>
              <td className="py-1 pr-3 text-right font-mono">{b.question_count}</td>
              {cols.map((c) => (
                <td key={c.key} className={`py-1 pr-3 text-right font-mono ${c.cls}`}>{sum(b[c.key])}</td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      {done && b.bank_id && (
        <Link href={`${bankBase}/${b.bank_id}`} className={`${btnSecondary} inline-block`}>
          {t("bank.import.openBank")}
        </Link>
      )}
    </div>
  );
}

export function ImportReportView({ report, done, bankBase }: { report: ImportReport; done: boolean; bankBase: string }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      {done ? (
        <div className="flex items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
          <CheckCircle2 className="h-7 w-7 flex-shrink-0 text-emerald-600" aria-hidden="true" />
          <h2 className="text-base font-bold text-slate-900">{t("bank.import.doneTitle")}</h2>
        </div>
      ) : (
        <div className={`flex items-center gap-2 rounded-2xl border p-4 text-sm font-bold ${report.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
          {report.ok ? <CheckCircle2 className="h-5 w-5" aria-hidden="true" /> : <AlertCircle className="h-5 w-5" aria-hidden="true" />}
          {report.ok ? t("bank.import.okTitle") : t("bank.import.errorTitle", { count: report.errors.length })}
        </div>
      )}
      {report.banks.map((b, i) => (
        <BankSummary key={`${b.root}-${b.bank_id ?? i}`} b={b} done={done} bankBase={bankBase} />
      ))}
      <div className="flex items-center gap-2 text-xs text-slate-600">
        <ImageIcon className="h-4 w-4" aria-hidden="true" />
        {t(done ? "bank.import.imagesDone" : "bank.import.images", {
          total: report.images_total,
          new: report.images_new,
          existing: report.images_existing,
        })}
      </div>
      <ImportIssues issues={report.errors} kind="error" />
      <ImportIssues issues={report.warnings} kind="warning" />
      {(report.errors.length > 0 || report.warnings.length > 0) && (
        <p className="text-[11px] text-slate-500">{t("bank.import.rowHint")}</p>
      )}
    </div>
  );
}
