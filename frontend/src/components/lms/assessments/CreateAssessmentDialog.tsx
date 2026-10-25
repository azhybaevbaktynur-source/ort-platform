"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { createAssessment } from "@/lib/lms/assessments";
import type { AssessmentPreset, AssessmentStaffOut } from "@/lib/lms/assessmentTypes";
import { useTemplateUi } from "@/lib/lms/templates";
import { cleanLocalized } from "@/lib/lms/localized";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { btnPrimary, btnSecondary, inputCls, labelCls } from "@/components/lms/content/ui";
import { AssessmentError } from "./AssessmentError";
import { Modal } from "./Modal";

export function CreateAssessmentDialog({
  open, courseId, courseLanguages, defaultLanguage, onCreated, onCancel,
}: {
  open: boolean;
  courseId: string;
  courseLanguages: Lang[];
  defaultLanguage: Lang;
  onCreated: (a: AssessmentStaffOut) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const ui = useTemplateUi();
  const presets = ui.assessmentPresets;
  const subjects = ui.subjectKeys;
  const firstSubject = subjects[0] ?? "";
  const [title, setTitle] = useState<LocalizedText>({});
  const [preset, setPreset] = useState<AssessmentPreset>("none");
  const [languages, setLanguages] = useState<Lang[]>([defaultLanguage]);
  const [subject, setSubject] = useState<string>(firstSubject);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (open) { setTitle({}); setPreset("none"); setLanguages([defaultLanguage]); setSubject(firstSubject); setError(null); }
  }, [open, defaultLanguage, firstSubject]);

  const toggle = (l: Lang) => {
    setLanguages((cur) => (cur.includes(l) ? (cur.length > 1 ? cur.filter((x) => x !== l) : cur) : courseLanguages.filter((x) => cur.includes(x) || x === l)));
  };
  const cleaned = cleanLocalized(title, courseLanguages);
  const valid = Object.keys(cleaned).length > 0;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      const a = await createAssessment(courseId, {
        title: cleaned, preset, languages, ...(preset === "ort_subject" ? { subject_key: subject } : {}),
      });
      onCreated(a);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} title={t("assessments.create.title")} onClose={onCancel} busy={busy}>
      <form onSubmit={submit} className="space-y-4">
        <LocalizedTextInput label={t("assessments.create.titleLabel")} languages={courseLanguages} defaultLanguage={defaultLanguage}
          value={title} onChange={setTitle} maxLength={200} required />
        {presets.length > 1 && <fieldset>
          <legend className={labelCls}>{t("assessments.create.preset")}</legend>
          <div className="space-y-2">
            {presets.map((p) => (
              <label key={p} className="flex items-start gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm">
                <input type="radio" name="preset" className="mt-1" checked={preset === p} onChange={() => setPreset(p)} />
                <span>
                  <span className="font-medium text-slate-900">{t(`assessments.presets.${p}.name`)}</span>
                  <span className="block text-xs text-slate-500">{t(`assessments.presets.${p}.hint`)}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>}
        {preset === "ort_subject" && (
          <div>
            <label className={labelCls} htmlFor="subject-key">{t("assessments.create.subject")}</label>
            <select id="subject-key" className={inputCls} value={subject} onChange={(e) => setSubject(e.target.value)}>
              {subjects.map((k) => <option key={k} value={k}>{t(`sections.${k}`)}</option>)}
            </select>
          </div>
        )}
        <fieldset>
          <legend className={labelCls}>{t("assessments.create.languages")}</legend>
          <div className="flex flex-wrap gap-3">
            {courseLanguages.map((l) => (
              <label key={l} className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-3 py-2 text-sm">
                <input type="checkbox" checked={languages.includes(l)} onChange={() => toggle(l)} />
                {t(`courses.languages.${l}`)}
              </label>
            ))}
          </div>
          <p className="mt-1 text-xs text-slate-500">{t("assessments.create.languagesHint")}</p>
        </fieldset>
        <AssessmentError error={error} />
        <div className="flex justify-end gap-2">
          <button type="button" className={btnSecondary} disabled={busy} onClick={onCancel}>{t("lms.common.cancel")}</button>
          <button type="submit" className={btnPrimary} disabled={busy || !valid}>{busy ? t("lms.common.loading") : t("assessments.create.submit")}</button>
        </div>
      </form>
    </Modal>
  );
}
