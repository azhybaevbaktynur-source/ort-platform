"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw, Upload } from "lucide-react";
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
import { cardCls, inputCls, labelCls } from "@/components/lms/content/ui";
import { btnPrimary, btnSecondary } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { importProfileLabelKey, templateUi } from "@/lib/lms/templates";
import { ImportReportView, type ExamSectionRef } from "./ImportReportView";
import { getAssessment } from "@/lib/lms/assessments"; // Phase 7b S7
import { ImportValidationFields } from "@/components/lms/examTemplates/ImportValidationFields"; // Phase 7b S4

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
  // --- Phase 7b S4: validation against a template exam (general format only; ORT format unchanged) ---
  const [validateId, setValidateId] = useState("");
  const [attach, setAttach] = useState(false);
  const general = !format;
  // --- Phase 7b S4 end ---
  // --- Phase 7b S7: the chosen exam's sections, so issues and the attach summary name sections by title ---
  const [examSections, setExamSections] = useState<ExamSectionRef[] | null>(null);
  useEffect(() => {
    if (!validateId) { setExamSections(null); return; }
    let alive = true;
    getAssessment(course.id, validateId)
      .then((a) => { if (alive) setExamSections(a.sections.map((s) => ({ key: s.key, title: s.title }))); })
      .catch(() => { if (alive) setExamSections(null); /* names fall back to the labels */ });
    return () => { alive = false; };
  }, [course.id, validateId]);
  const examRefs = general && validateId ? examSections : null;

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
    // Phase 7b S4
    assessmentId: general && validateId ? validateId : null,
    attachToAssessmentId: general && validateId && attach ? validateId : null,
  }), [file, language, format, targetBankId, canTarget, onConflict, general, validateId, attach]);

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
        <ImportReportView report={result} done bankBase={bankBase} examSections={examRefs} />
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
          {/* Phase 6b S5c (UX T11): a translated "Choose file" button and the file name instead of the browser's English control. */}
          <div className="flex flex-wrap items-center gap-3">
            <input
              id="imp-file" ref={fileRef} type="file" accept=".csv,.zip,text/csv,application/zip"
              disabled={busy !== null}
              onChange={(e) => pick(e.target.files?.[0] ?? null)}
              className="peer sr-only"
            />
            <label htmlFor="imp-file" aria-hidden="true"
              className={`${btnSecondary} cursor-pointer peer-focus-visible:ring-2 peer-focus-visible:ring-brand-600 peer-focus-visible:ring-offset-2 peer-disabled:cursor-not-allowed peer-disabled:opacity-60`}>
              <Upload className="h-4 w-4" aria-hidden="true" />{t("teaching.chooseFile")}
            </label>
            <span className="min-w-0 break-all text-sm text-slate-700">{file ? file.name : t("teaching.noFile")}</span>
          </div>
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

        {/* --- Phase 7b S4 --- */}
        {general && (
          <ImportValidationFields courseId={course.id} value={validateId} attach={attach} disabled={busy !== null}
            onChange={(id, att, langs) => {
              setValidateId(id); setAttach(att); invalidate();
              // S5: questions are attached only in the exam's languages; default the import language to one of them
              if (langs && langs.length && !langs.includes(language)) {
                const next = langs.find((l) => course.languages.includes(l as Lang));
                if (next) setLanguage(next as Lang);
              }
            }} />
        )}

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
          <ImportReportView report={preview} done={false} bankBase={bankBase} examSections={examRefs} />
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
