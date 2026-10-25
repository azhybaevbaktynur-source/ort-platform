"use client";

import React from "react";
import { Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { RichTextField } from "../RichTextField";
import { inputCls, labelCls } from "../ui";
import { btnSmall } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { blankNumeric, type QuestionForm } from "./formModel";

type Props = { form: QuestionForm; onChange: (patch: Partial<QuestionForm>) => void; disabled?: boolean };

export function TrueFalseFields({ form, onChange, disabled }: Props) {
  const { t } = useTranslation();
  return (
    <fieldset disabled={disabled}>
      <legend className={labelCls}>{t("bank.editor.correct")}</legend>
      <div className="flex gap-4">
        {[true, false].map((v) => (
          <label key={String(v)} className="flex items-center gap-1.5 text-sm text-slate-700">
            <input type="radio" name="tf" checked={form.tf === v} onChange={() => onChange({ tf: v })} />
            {t(v ? "bank.editor.true" : "bank.editor.false")}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function ComparisonFields({ form, onChange, disabled }: Props) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <RichTextField label={t("bank.editor.columnA")} rows={3} value={form.columnA} disabled={disabled} onChange={(v) => onChange({ columnA: v })} />
        <RichTextField label={t("bank.editor.columnB")} rows={3} value={form.columnB} disabled={disabled} onChange={(v) => onChange({ columnB: v })} />
      </div>
      <fieldset disabled={disabled}>
        <legend className={labelCls}>{t("bank.editor.correct")}</legend>
        <div className="space-y-1">
          {(["A", "B", "C", "D"] as const).map((k) => (
            <label key={k} className="flex items-center gap-2 text-sm text-slate-700">
              <input type="radio" name="cmp" checked={form.compCorrect === k} onChange={() => onChange({ compCorrect: k })} />
              <span className="font-semibold">{k}.</span> {t(`bank.types.comparison.labels.${k}`)}
            </label>
          ))}
        </div>
      </fieldset>
    </div>
  );
}

export function NumericFields({ form, onChange, disabled }: Props) {
  const { t } = useTranslation();
  const set = (i: number, patch: Partial<QuestionForm["numeric"][number]>) =>
    onChange({ numeric: form.numeric.map((n, j) => (j === i ? { ...n, ...patch } : n)) });
  return (
    <div className="space-y-2">
      <span className={labelCls}>{t("bank.editor.acceptedAnswers")}</span>
      {form.numeric.map((n, i) => (
        <div key={i} className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 p-2">
          <select disabled={disabled} className={`${inputCls} w-auto`} value={n.kind} aria-label={t("bank.editor.answerKind")}
            onChange={(e) => set(i, { kind: e.target.value as "exact" | "range" })}>
            <option value="exact">{t("bank.editor.kindExact")}</option>
            <option value="range">{t("bank.editor.kindRange")}</option>
          </select>
          {n.kind === "exact" ? (
            <>
              <label className="text-xs text-slate-600">{t("bank.editor.value")}
                <input disabled={disabled} inputMode="decimal" className={`${inputCls} mt-0.5 w-32`} value={n.value} onChange={(e) => set(i, { value: e.target.value })} />
              </label>
              <label className="text-xs text-slate-600">{t("bank.editor.margin")}
                <input disabled={disabled} inputMode="decimal" className={`${inputCls} mt-0.5 w-24`} value={n.margin} onChange={(e) => set(i, { margin: e.target.value })} />
              </label>
            </>
          ) : (
            <>
              <label className="text-xs text-slate-600">{t("bank.editor.min")}
                <input disabled={disabled} inputMode="decimal" className={`${inputCls} mt-0.5 w-28`} value={n.min} onChange={(e) => set(i, { min: e.target.value })} />
              </label>
              <label className="text-xs text-slate-600">{t("bank.editor.max")}
                <input disabled={disabled} inputMode="decimal" className={`${inputCls} mt-0.5 w-28`} value={n.max} onChange={(e) => set(i, { max: e.target.value })} />
              </label>
            </>
          )}
          <button type="button" disabled={disabled || form.numeric.length <= 1} className={btnSmall}
            onClick={() => onChange({ numeric: form.numeric.filter((_, j) => j !== i) })} aria-label={t("bank.editor.removeAnswer")}>
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
      ))}
      <button type="button" disabled={disabled || form.numeric.length >= 10} className={btnSmall}
        onClick={() => onChange({ numeric: [...form.numeric, blankNumeric()] })}>
        <Plus className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" />{t("bank.editor.addAnswer")}
      </button>
      <p className="text-xs text-slate-500">{t("bank.editor.numericHint")}</p>
    </div>
  );
}

export function ShortTextFields({ form, onChange, disabled }: Props) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2">
      <label className={labelCls} htmlFor="short-answers">{t("bank.editor.acceptedAnswers")}</label>
      <textarea id="short-answers" rows={4} disabled={disabled} className={inputCls} value={form.shortAnswers}
        onChange={(e) => onChange({ shortAnswers: e.target.value })} />
      <p className="text-xs text-slate-500">{t("bank.editor.shortHint")}</p>
      <label className="flex items-center gap-1.5 text-sm text-slate-700">
        <input type="checkbox" disabled={disabled} checked={form.caseSensitive} onChange={(e) => onChange({ caseSensitive: e.target.checked })} />
        {t("bank.editor.caseSensitive")}
      </label>
    </div>
  );
}

export function EssayFields({ form, onChange, disabled }: Props) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-slate-700">{t("bank.editor.wordLimit")}
        <input type="number" min={1} max={5000} disabled={disabled} className={`${inputCls} mt-1 w-40`} value={form.wordLimit}
          onChange={(e) => onChange({ wordLimit: e.target.value })} />
      </label>
      <RichTextField label={t("bank.editor.rubric")} rows={3} value={form.rubric} disabled={disabled} onChange={(v) => onChange({ rubric: v })} />
      <p className="text-xs text-slate-500">{t("bank.editor.rubricHint")}</p>
    </div>
  );
}
