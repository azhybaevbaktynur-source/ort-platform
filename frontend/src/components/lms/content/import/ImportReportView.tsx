"use client";

import React from "react";
import Link from "next/link";
import { AlertCircle, AlertTriangle, CheckCircle2, ImageIcon } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { ImportBankSummary, ImportIssue, ImportReport } from "@/lib/lms/contentImport";
import { questionTypeTitleKey } from "@/lib/lms/blocks";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { cardCls } from "@/components/lms/content/ui";
import { btnSecondary } from "@/components/lms/course/staffUi"; // Phase 6b S5c

const sum = (o: Record<string, number>) => Object.values(o).reduce((a, n) => a + n, 0);

// --- Phase 7b S7: names instead of keys for the template issue codes (types by name, sections by the exam's title) ---
/** One section of the exam chosen for validation (in order). */
export interface ExamSectionRef {
  key: string | null;
  title: LocalizedText | null;
}
type SectionNamer = (label: string, position?: number) => string;

/** Section label of the importer (key, title or `section_<n>`) -> the exam section's title ("Раздел n" fallback). */
export function useSectionNamer(sections: ExamSectionRef[] | null | undefined): SectionNamer {
  const { lang, t } = useTranslation();
  return (label: string, position?: number) => {
    const list = sections ?? [];
    const low = label.trim().toLowerCase();
    let i = position !== undefined && position < list.length ? position : list.findIndex((s) => s.key === label);
    if (i < 0) i = list.findIndex((s) => Object.values(s.title ?? {}).some((v) => (v ?? "").trim().toLowerCase() === low));
    const m = /^section_(\d+)$/.exec(label);
    if (i < 0 && m && Number(m[1]) <= list.length) i = Number(m[1]) - 1;
    if (i < 0) {
      const k = `sections.${label}`;
      return t(k) === k ? (m ? t("examTemplates.picker.sectionN", { n: Number(m[1]) }) : label) : t(k);
    }
    const s = list[i];
    const title = pickLocalized(s.title, lang as Lang);
    if (title) return title;
    const k = `sections.${s.key ?? ""}`;
    return s.key ? (t(k) === k ? s.key : t(k)) : t("examTemplates.picker.sectionN", { n: i + 1 });
  };
}

/** Codes of the template validation (general format only); their `type` / `allowed` / `section` params get names. */
const TEMPLATE_CODES = new Set(["type_not_allowed_in_section", "passage_not_allowed", "count_below_min", "count_above_max"]);

export function ImportIssues({ issues, kind, sectionName }: { issues: ImportIssue[]; kind: "error" | "warning"; sectionName?: SectionNamer }) {
  const { t } = useTranslation();
  if (issues.length === 0) return null;
  const isError = kind === "error";
  const typeName = (ty: unknown) => {
    const k = questionTypeTitleKey(String(ty));
    return t(k) === k ? String(ty) : t(k);
  };
  const text = (issue: ImportIssue) => {
    const key = `bank.import.issues.${issue.code}`;
    const named = TEMPLATE_CODES.has(issue.code);
    const params = Object.fromEntries(
      Object.entries(issue.params || {}).map(([k, v]) => {
        if (named && k === "type") return [k, typeName(v)];
        if (named && k === "allowed" && Array.isArray(v)) return [k, v.map(typeName).join(", ")];
        if (named && k === "section" && sectionName) return [k, sectionName(String(v ?? ""))];
        return [k, Array.isArray(v) ? v.join(", ") : String(v ?? "")];
      }),
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

function AttachedSummary({ attached, bankBase, sectionName }: {
  attached: NonNullable<ImportReport["attached"]>;
  bankBase: string;
  sectionName: SectionNamer;
}) {
  const { t } = useTranslation();
  const skipped = sum(attached.skipped || {});
  const positions = attached.section_positions ?? {};
  const name = (label: string) => sectionName(label, positions[label]);
  // S7: too_many_items names the full section and its maximum (backend `skip_details`)
  const full = (attached.skip_details ?? []).filter((d) => d.code === "too_many_items");
  // the builder's skip codes (item_duplicate, item_language_mismatch, too_many_items, ...) share the lms.errors wording
  const reason = (code: string) => {
    const k = `lms.errors.${code}`;
    const v = t(k);
    return v === k ? code : v;
  };
  const examHref = `${bankBase.replace(/\/bank$/, "")}/assessments/${attached.assessment_id}/edit`;
  return (
    <div role="status" className={`${cardCls} space-y-2 border-emerald-200 bg-emerald-50 text-sm text-slate-800`}>
      <p className="font-semibold">{t("examTemplates.import.attached", { count: attached.added })}</p>
      {Object.keys(attached.sections || {}).length > 0 && (
        <ul className="space-y-0.5">
          {Object.entries(attached.sections).map(([sec, n]) => <li key={sec} className="break-words">{name(sec)}: {n}</li>)}
        </ul>
      )}
      {skipped > 0 && (
        <div className="text-amber-900">
          <p>{t("examTemplates.import.attachedSkipped", { count: skipped })}</p>
          <ul className="list-disc pl-5">
            {Object.entries(attached.skipped).map(([code, n]) => code === "too_many_items" ? (
              full.length > 0 ? full.map((d) => (
                <li key={`${code}-${d.position}`} className="break-words">
                  {d.scope === "exam"
                    ? t("examTemplates.import.tooManyItemsExam", { max: d.max })
                    : t("examTemplates.import.tooManyItems", { section: sectionName(d.section, d.position), max: d.max })} ({d.count})
                </li>
              )) : <li key={code} className="break-words">{t("examTemplates.import.tooManyItemsGeneric")} ({n})</li>
            ) : <li key={code} className="break-words">{reason(code)} ({n})</li>)}
          </ul>
        </div>
      )}
      <Link href={examHref} className={`${btnSecondary} inline-block`}>{t("examTemplates.import.openExam")}</Link>
    </div>
  );
}

export function ImportReportView({ report, done, bankBase, examSections }: {
  report: ImportReport;
  done: boolean;
  bankBase: string;
  /** Phase 7b S7: sections of the exam chosen for validation (general format), for names in issues. */
  examSections?: ExamSectionRef[] | null;
}) {
  const { t } = useTranslation();
  const sectionName = useSectionNamer(examSections);
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
      {/* --- Phase 7b S5: questions added to a template exam (commit with "Add to this exam") --- */}
      {done && report.attached && <AttachedSummary attached={report.attached} bankBase={bankBase} sectionName={sectionName} />}
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
      <ImportIssues issues={report.errors} kind="error" sectionName={examSections ? sectionName : undefined} />
      <ImportIssues issues={report.warnings} kind="warning" sectionName={examSections ? sectionName : undefined} />
      {(report.errors.length > 0 || report.warnings.length > 0) && (
        <p className="text-[11px] text-slate-500">{t("bank.import.rowHint")}</p>
      )}
    </div>
  );
}
