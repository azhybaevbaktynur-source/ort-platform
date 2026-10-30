"use client";

// Phase 9 S4: renders an enrollment form (the builder's Preview tab and the student apply page; PHASE_9_DESIGN
// §4.10, §8.4). One field per row; choice fields are stacked radios / checkboxes; errors name the field, never echo
// the value. Answers stay in React state only (PII of possible minors: no storage, no logging).
import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { AnswerValue, FieldOut, Lang, LocalizedText } from "@/lib/lms/types";
import { TEXT_LIMITS } from "@/lib/lms/enrollmentForms";
import { Input, Textarea, cn } from "@/components/ui";

export type Answers = Record<string, AnswerValue>;

export interface RenderableForm {
  title: LocalizedText | null;
  intro: LocalizedText | null;
  fields: FieldOut[];
}

function isEmpty(v: AnswerValue | undefined): boolean {
  return v === undefined || v === null || (typeof v === "string" && v.trim() === "") || (Array.isArray(v) && v.length === 0);
}

export function textLimit(f: FieldOut): number | null {
  if (f.type !== "short_text" && f.type !== "long_text") return null;
  const lim = TEXT_LIMITS[f.type];
  return Math.min(f.max_len ?? lim.def, lim.max);
}

/** Client-side checks mirroring the server (required, length, options); the server stays authoritative. */
export function validateAnswers(fields: FieldOut[], values: Answers): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of fields) {
    const v = values[f.key];
    if (isEmpty(v)) {
      if (f.required) out[f.key] = "required";
      continue;
    }
    const limit = textLimit(f);
    if (limit !== null && typeof v === "string" && v.trim().length > limit) out[f.key] = "too_long";
    if (f.type === "number" && (typeof v !== "string" || !Number.isFinite(Number(String(v).replace(",", "."))))) {
      out[f.key] = "bad_format";
    } else if (f.type === "number" && f.bounds) {
      const n = Number(String(v).replace(",", "."));
      if ((f.bounds.min != null && n < f.bounds.min) || (f.bounds.max != null && n > f.bounds.max)) out[f.key] = "bad_format";
    }
  }
  return out;
}

/** The payload for `POST .../applications`: empty optional answers dropped, numbers converted. */
export function answersPayload(fields: FieldOut[], values: Answers): Answers {
  const out: Answers = {};
  for (const f of fields) {
    const v = values[f.key];
    if (isEmpty(v)) continue;
    out[f.key] = f.type === "number" && typeof v === "string" ? Number(v.replace(",", ".")) : typeof v === "string" ? v.trim() : v;
  }
  return out;
}

export function FormRenderer({
  form, lang, defaultLanguage, values, onChange, errors = {}, disabled = false, idPrefix = "ef",
}: {
  form: RenderableForm;
  lang: string;
  defaultLanguage: Lang;
  values: Answers;
  onChange: (key: string, value: AnswerValue) => void;
  errors?: Record<string, string>;
  disabled?: boolean;
  idPrefix?: string;
}) {
  const { t } = useTranslation();
  const L = (v: LocalizedText | null | undefined) => pickLocalized(v ?? null, lang as Lang, defaultLanguage);
  const intro = L(form.intro);
  const errorText = (key: string) => (errors[key] ? t(`applications.answerErrors.${errors[key]}`) : undefined);

  return (
    <div className="space-y-5">
      {intro && <p className="whitespace-pre-line text-base leading-6 text-slate-700">{intro}</p>}
      {form.fields.length === 0 && <p className="text-sm leading-6 text-slate-600">{t("enrollmentForm.preview.noFields")}</p>}
      {form.fields.map((f) => {
        const id = `${idPrefix}-${f.key}`;
        const label = L(f.label) || f.key;
        const hint = L(f.help) || undefined;
        const err = errorText(f.key);
        const value = values[f.key];
        const optional = !f.required;
        if (f.type === "single_choice" || f.type === "multi_choice") {
          const multi = f.type === "multi_choice";
          const selected = new Set(Array.isArray(value) ? value : typeof value === "string" ? [value] : []);
          return (
            <fieldset key={f.key} aria-describedby={err ? `${id}-error` : hint ? `${id}-hint` : undefined}>
              <legend className="mb-1 text-sm font-medium leading-6 text-slate-800">
                {label}
                {optional && <span className="ml-1 font-normal text-slate-600">{t("ui.optional")}</span>}
              </legend>
              {hint && <p id={`${id}-hint`} className="mb-1 text-sm leading-6 text-slate-600">{hint}</p>}
              <div className="space-y-0.5">
                {(f.options ?? []).map((o) => {
                  const oid = `${id}-${o.key}`;
                  const checked = selected.has(o.key);
                  return (
                    <label key={o.key} htmlFor={oid} className={cn("flex min-h-11 items-start gap-3 rounded-lg px-1 py-2.5", disabled ? "cursor-not-allowed" : "cursor-pointer")}>
                      <input id={oid} type={multi ? "checkbox" : "radio"} name={id} value={o.key} checked={checked} disabled={disabled}
                        aria-invalid={err ? true : undefined}
                        onChange={() => {
                          if (!multi) return onChange(f.key, o.key);
                          const next = new Set(selected);
                          if (checked) next.delete(o.key); else next.add(o.key);
                          onChange(f.key, (f.options ?? []).map((x) => x.key).filter((k) => next.has(k)));
                        }}
                        className="mt-0.5 h-5 w-5 shrink-0 accent-brand-600" />
                      <span className="text-base leading-6 text-slate-800 sm:text-sm">{L(o.label) || o.key}</span>
                    </label>
                  );
                })}
              </div>
              {err && <p id={`${id}-error`} className="mt-1 text-sm font-medium text-danger-700">{err}</p>}
            </fieldset>
          );
        }
        const common = {
          id, label, hint, error: err, optional, disabled,
          value: typeof value === "string" || typeof value === "number" ? String(value) : "",
        };
        if (f.type === "long_text") {
          return <Textarea key={f.key} {...common} rows={4} maxLength={textLimit(f) ?? undefined}
            onChange={(e) => onChange(f.key, e.target.value)} />;
        }
        const inputType = f.type === "number" ? "text" : f.type === "date" ? "date" : f.type === "email" ? "email" : f.type === "phone" ? "tel" : "text";
        return (
          <Input key={f.key} {...common} type={inputType}
            inputMode={f.type === "number" ? "decimal" : f.type === "phone" ? "tel" : undefined}
            autoComplete={f.type === "email" ? "email" : f.type === "phone" ? "tel" : "off"}
            maxLength={textLimit(f) ?? (f.type === "email" ? 255 : f.type === "phone" ? 24 : undefined)}
            onChange={(e) => onChange(f.key, e.target.value)} />
        );
      })}
    </div>
  );
}
