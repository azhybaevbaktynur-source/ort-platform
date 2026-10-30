"use client";

// Phase 9 S4: Preview tab of the enrollment form (PHASE_9_DESIGN 8.1): the form exactly as a student sees it, with
// the privacy note and the client-side checks; nothing is sent. Shows the builder's current (possibly unsaved) state.
import React, { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { AnswerValue, Lang } from "@/lib/lms/types";
import { Button } from "@/components/ui";
import { FormRenderer, validateAnswers, type Answers, type RenderableForm } from "./FormRenderer";

export function FormPreview({ form, defaultLanguage, languages }: { form: RenderableForm; defaultLanguage: Lang; languages: Lang[] }) {
  const { lang: uiLang, t } = useTranslation();
  const [lang, setLang] = useState<Lang>(languages.includes(uiLang as Lang) ? (uiLang as Lang) : defaultLanguage);
  const [values, setValues] = useState<Answers>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [checked, setChecked] = useState(false);
  const title = pickLocalized(form.title, lang, defaultLanguage);

  return (
    <div className="space-y-4">
      <p className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-700">{t("enrollmentForm.preview.note")}</p>
      {languages.length > 1 && (
        <div role="group" aria-label={t("enrollmentForm.preview.language")} className="flex flex-wrap gap-2">
          {languages.map((l) => (
            <Button key={l} size="sm" variant={l === lang ? "primary" : "secondary"} aria-pressed={l === lang} onClick={() => setLang(l)}>
              {t(`courses.languages.${l}`)}
            </Button>
          ))}
        </div>
      )}
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
        {title && <h2 className="mb-4 text-xl font-semibold leading-7 text-slate-900">{title}</h2>}
        <div className="mb-5 flex items-start gap-3 rounded-2xl border border-brand-200 bg-brand-50 p-4 text-base leading-6 text-brand-900 sm:text-sm">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
          <p>{t("applications.privacyNote")}</p>
        </div>
        <FormRenderer form={form} lang={lang} defaultLanguage={defaultLanguage} values={values} errors={errors} idPrefix="preview"
          onChange={(key: string, v: AnswerValue) => {
            setValues((p) => ({ ...p, [key]: v }));
            setChecked(false);
            if (errors[key]) setErrors((e) => { const n = { ...e }; delete n[key]; return n; });
          }} />
        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button onClick={() => { setErrors(validateAnswers(form.fields, values)); setChecked(true); }}>
            {t("enrollmentForm.preview.check")}
          </Button>
          {checked && Object.keys(errors).length === 0 && (
            <p role="status" className="text-sm font-medium text-success-700">{t("enrollmentForm.preview.checkOk")}</p>
          )}
        </div>
      </div>
    </div>
  );
}
