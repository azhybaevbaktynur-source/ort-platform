"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { listBanks } from "@/lib/lms/content";
import type { BankOut } from "@/lib/lms/contentTypes";
import {
  IMPORT_LIMITS, commitImport, previewImport,
  type ImportConflictPolicy, type ImportExamType, type ImportReport,
} from "@/lib/lms/contentImport";
import type { Lang } from "@/lib/lms/types";
import { ContentError } from "@/components/lms/content/ContentError";
import { btnPrimary, btnSecondary, cardCls, inputCls, labelCls } from "@/components/lms/content/ui";
import { importProfileLabelKey, templateUi } from "@/lib/lms/templates";
import { ImportReportView } from "./ImportReportView";

export function ImportPanel() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  // Formats come from the course template (T11): template profiles + the general format; a general
  // course has no profiles, shows no format select and sends exam_type = null.
  const ui = templateUi(course);
  const formats: ("" | ImportExamType)[] = ui.importerProfiles.length ? [...ui.importerProfiles, ""] : [];
  const bankBase = `/${lang}/courses/${course.id}/bank`;
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState<Lang>(course.languages.includes("ky") ? "ky" : course.languages[0]);
  const [format, setFormat] = useState<"" | ImportExamType>(ui.defaultImportProfile);
  const [targetBankId, setTargetBankId] = useState("");
  const [onConflict, setOnConflict] = useState<ImportConflictPolicy>("skip");
  const [banks, setBanks] = useState<BankOut[]>([]);
  const [preview, setPreview] = useState<ReportState | null>(null);
  const [result, setResult] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState<"preview" | "commit" | null>(null);
  const [error, setError] = useState<unknown>(null);

  const isZip = !!file && file.name.toLowerCase().endsWith(".zip");
  const canTarget = !!file && !isZip;

  useEffect(() => {
    let alive = true;
    listBanks(course.id, { limit: 100 })
      .then((p) => { if (alive) setBanks(p.items); })
      .catch(() => { /* target list is optional; creating a new bank still works */ });
    return () => { alive = false; };
  }, [course.id]);

  const params = useMemo(() => file && ({
    file, language, examType: format || null, targetBankId: canTarget ? targetBankId || null : null, onConflict,
  }), [file, language, format, targetBankId, canTarget, onConflict]);

  const invalidate = () => { setPreview(null); setResult(null); setError(null); };

  const pick = (f: File | null) => { setFile(f); invalidate(); };

  const reset = () => {
    setFile(null);
    invalidate();
    if (fileRef.current) fileRef.current.value = "";
  };

  const run = async (kind: "preview" | "commit") => {
    if (!params) return;
    setBusy(kind);
    setError(null);
    try {
      if (kind === "preview") {
        setPreview(await previewImport(course.id, params));
        setResult(null);
      } else {
        const r = await commitImport(course.id, params);
        if (r.committed) setResult(r);
        else { setPreview(r); setResult(null); }
      }
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  if (result) {
    return (
      <div className="space-y-4">
        <ImportReportView report={result} done bankBase={bankBase} />
        <button type="button" onClick={reset} className={btnSecondary}>{t("bank.import.reset")}</button>
      </div>
    );
  }

  const total = preview ? preview.banks.reduce((n, b) => n + b.question_count, 0) : 0;

  return (
    <div className="space-y-4">
      <div className={`${cardCls} space-y-4`}>
        <p className="text-xs text-slate-600">{t("bank.import.subtitle")}</p>
        <div>
          <label htmlFor="imp-file" className={labelCls}>{t("bank.import.fileLabel")}</label>
          <input
            id="imp-file" ref={fileRef} type="file" accept=".csv,.zip,text/csv,application/zip"
            disabled={busy !== null}
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-slate-700 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium"
          />
          <p className="mt-1 text-xs text-slate-500">
            {t("bank.import.limits", { mb: IMPORT_LIMITS.uploadMb, rows: IMPORT_LIMITS.rows, images: IMPORT_LIMITS.images })}
          </p>
          {isZip && <p className="mt-1 text-xs text-slate-600">{t("bank.import.detectedZip")}</p>}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="imp-lang" className={labelCls}>{t("bank.import.language")}</label>
            <select id="imp-lang" className={inputCls} value={language} disabled={busy !== null}
              onChange={(e) => { setLanguage(e.target.value as Lang); invalidate(); }}>
              {course.languages.map((l) => <option key={l} value={l}>{t(`courses.languages.${l}`)}</option>)}
            </select>
            <p className="mt-1 text-xs text-slate-500">{t("bank.import.languageNote")}</p>
          </div>
          {formats.length > 0 && <div>
            <label htmlFor="imp-format" className={labelCls}>{t("bank.import.format")}</label>
            <select id="imp-format" className={inputCls} value={format} disabled={busy !== null}
              onChange={(e) => { setFormat(e.target.value as "" | ImportExamType); invalidate(); }}>
              {formats.map((f) => <option key={importProfileLabelKey(f)} value={f}>{t(importProfileLabelKey(f))}</option>)}
            </select>
            <p className="mt-1 text-xs text-slate-500">{t(format ? "bank.import.formatOrtNote" : "bank.import.formatGeneralNote")}</p>
          </div>}
        </div>

        <div>
          <label htmlFor="imp-target" className={labelCls}>{t("bank.import.target")}</label>
          <select id="imp-target" className={inputCls} value={canTarget ? targetBankId : ""} disabled={!canTarget || busy !== null}
            onChange={(e) => { setTargetBankId(e.target.value); invalidate(); }}>
            <option value="">{t("bank.import.targetNew")}</option>
            {banks.map((b) => <option key={b.id} value={b.id}>{b.title}</option>)}
          </select>
          <p className="mt-1 text-xs text-slate-500">{t(isZip ? "bank.import.targetZipNote" : "bank.import.targetNote")}</p>
        </div>

        <fieldset>
          <legend className={labelCls}>{t("bank.import.conflict.label")}</legend>
          <div className="space-y-1.5">
            {(["skip", "overwrite"] as const).map((v) => (
              <label key={v} className="flex items-start gap-2 text-sm text-slate-700">
                <input type="radio" name="on_conflict" value={v} checked={onConflict === v} disabled={busy !== null}
                  onChange={() => setOnConflict(v)} className="mt-1" />
                <span>
                  <span className="font-medium">{t(`bank.import.conflict.${v}`)}</span>
                  <span className="block text-xs text-slate-500">{t(`bank.import.conflict.${v}Hint`)}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <button type="button" onClick={() => void run("preview")} disabled={!file || busy !== null} className={`${btnPrimary} flex w-full items-center justify-center gap-2`}>
          {busy === "preview" && <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {t(busy === "preview" ? "bank.import.checking" : "bank.import.check")}
        </button>
      </div>

      <ContentError error={error} />

      {preview && (
        <div className="space-y-4">
          <ImportReportView report={preview} done={false} bankBase={bankBase} />
          <div className="flex flex-col gap-2 sm:flex-row">
            <button type="button" onClick={() => void run("commit")} disabled={!preview.ok || busy !== null}
              className={`${btnPrimary} flex flex-1 items-center justify-center gap-2`}>
              {busy === "commit" && <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {t(busy === "commit" ? "bank.import.importing" : "bank.import.confirm", { count: total })}
            </button>
            <button type="button" onClick={reset} disabled={busy !== null} className={btnSecondary}>{t("bank.import.reset")}</button>
          </div>
        </div>
      )}
    </div>
  );
}

type ReportState = ImportReport;
