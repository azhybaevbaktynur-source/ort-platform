"use client";

import React, { useState } from "react";
import { ImagePlus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  DIFFICULTIES, ORT_SECTIONS, QUESTION_TYPES, type PassageSummaryOut, type QuestionType,
} from "@/lib/lms/contentTypes";
import type { Lang } from "@/lib/lms/types";
import { ImagePicker } from "./ImagePicker";
import { RichTextField } from "./RichTextField";
import { ChoiceFields } from "./types/ChoiceFields";
import { ComparisonFields, EssayFields, NumericFields, ShortTextFields, TrueFalseFields } from "./types/SimpleFields";
import type { QuestionForm } from "./types/formModel";
import { cardCls, inputCls, labelCls } from "./ui";
import { btnSmall } from "@/components/lms/course/staffUi";

/** Phase 7c UX: where a validation error of the quiz card is shown (values are translated messages). */
export interface QuestionFormErrors {
  stem?: string;
  points?: string;
  image?: string;
  /** The per-type answer fields (answers, columns, accepted answers). */
  answers?: string;
  /** The i18n key of a client-side answers error (which answer controls are marked invalid). */
  answersKey?: string;
  explanation?: string;
  other?: string;
}

/**
 * Phase 7c S3 (PHASE_7C_DESIGN 8.4): the body of the question form (type, language, points, stem, image, per-type
 * fields, explanation, meta grid), extracted from `QuestionEditor` without any change to its markup, so the Bank tab
 * (and the ORT bank screens) render exactly as before. The quiz editor card renders it with its own options.
 */
export function QuestionCardForm({
  form, onChange, disabled, courseId, languages, typeOptions = QUESTION_TYPES, lockType = false, lockLanguage = false,
  passages = [], showMeta = true, idPrefix = "q", keyboardAnswers = false, compact = false, errors = {}, hideLockedLanguage = false,
}: {
  form: QuestionForm;
  onChange: (patch: Partial<QuestionForm>) => void;
  disabled?: boolean;
  courseId: string;
  /** Languages offered by the language select (when not locked). */
  languages: Lang[];
  typeOptions?: QuestionType[];
  /** Show the type as text instead of a select (the Bank tab when editing). */
  lockType?: boolean;
  lockLanguage?: boolean;
  passages?: PassageSummaryOut[];
  /** The meta grid (section, topic, difficulty, tags, passage). */
  showMeta?: boolean;
  /** Prefix of the element ids, unique per form on a page. */
  idPrefix?: string;
  /** Phase 7c S5: Enter / Backspace manage the answers (the quiz card; off in the Bank tab). */
  keyboardAnswers?: boolean;
  /** Phase 7c UX (opt-in, the quiz card; default = the Bank tab's rendering): no inner boxes, the preview only for math
   * or markup, one line per answer, and the question image behind a small "Add image" button. */
  compact?: boolean;
  /** Phase 7c UX (the quiz card): validation errors shown under their fields. */
  errors?: QuestionFormErrors;
  /** Phase 7c UX (the quiz card): no language row when the language is locked (one-language quiz or existing card). */
  hideLockedLanguage?: boolean;
}) {
  const { t } = useTranslation();
  const patch = onChange;
  const fieldProps = { form, onChange: patch, disabled };
  const id = (s: string) => `${idPrefix}-${s}`;
  const [imageOpen, setImageOpen] = useState(false);
  const showLanguage = !(hideLockedLanguage && lockLanguage);
  const box = compact ? "" : cardCls;
  const err = (k: keyof QuestionFormErrors) => errors[k] || null;
  const answersErr = err("answers");
  const choiceTypes = form.type === "single_choice" || form.type === "multiple_answers";
  const typeFields = (
    <>
      {form.type === "true_false" && <TrueFalseFields {...fieldProps} />}
      {form.type === "comparison" && <ComparisonFields {...fieldProps} />}
      {form.type === "numeric" && <NumericFields {...fieldProps} />}
      {form.type === "short_text" && <ShortTextFields {...fieldProps} />}
      {form.type === "essay" && <EssayFields {...fieldProps} />}
    </>
  );
  return (
    <>
      <div className={`${box} grid gap-3 ${showLanguage ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
        <div>
          <span className={labelCls}>{t("bank.editor.type")}</span>
          {lockType ? (
            <p className="py-2 text-sm font-semibold text-slate-900">{t(`bank.types.${form.type}.name`)}</p>
          ) : (
            <select className={inputCls} disabled={disabled} value={form.type} onChange={(e) => patch({ type: e.target.value as QuestionType })}
              aria-label={idPrefix === "q" ? undefined : t("bank.editor.type")}>
              {typeOptions.map((ty) => (
                <option key={ty} value={ty}>{t(`bank.types.${ty}.name`)}</option>
              ))}
            </select>
          )}
        </div>
        {showLanguage && (
          <div>
            <label className={labelCls} htmlFor={id("lang")}>{t("bank.editor.language")}</label>
            {lockLanguage ? (
              <p className="py-2 text-sm font-semibold text-slate-900">{t(`courses.languages.${form.language}`)}</p>
            ) : (
              <select id={id("lang")} className={inputCls} disabled={disabled} value={form.language} onChange={(e) => patch({ language: e.target.value as Lang })}>
                {languages.map((l) => <option key={l} value={l}>{t(`courses.languages.${l}`)}</option>)}
              </select>
            )}
          </div>
        )}
        <div>
          <label className={labelCls} htmlFor={id("points")}>{t("bank.editor.points")}</label>
          <input id={id("points")} type="number" min={0} max={1000} step="0.01" className={`${inputCls}${err("points") ? " border-red-500" : ""}`} disabled={disabled} value={form.points}
            aria-invalid={err("points") ? true : undefined} aria-describedby={err("points") ? id("points-err") : undefined}
            onChange={(e) => patch({ points: e.target.value })} />
          {err("points") && <p id={id("points-err")} className="mt-1 text-sm text-red-700">{err("points")}</p>}
        </div>
      </div>

      <div className={`${box} space-y-4`}>
        <p className="text-xs text-slate-500">{t(`bank.types.${form.type}.hint`)}</p>
        <RichTextField label={t("bank.editor.stem")} rows={compact ? 3 : 5} value={form.stem} disabled={disabled} onChange={(v) => patch({ stem: v })}
          {...(compact ? { smartPreview: true, error: err("stem") } : {})} />
        {compact && !form.image && !imageOpen ? (
          <button type="button" disabled={disabled} className={btnSmall} onClick={() => setImageOpen(true)}>
            <ImagePlus className="mr-1 inline h-4 w-4" aria-hidden="true" />{t("quizEditor.card.addImage")}
          </button>
        ) : (
          <ImagePicker courseId={courseId} label={t("bank.editor.image")} value={form.image} disabled={disabled} onChange={(img) => patch({ image: img })} />
        )}
        {err("image") && <p className="text-sm text-red-700">{err("image")}</p>}
        {choiceTypes && <ChoiceFields courseId={courseId} {...fieldProps} keyboardAnswers={keyboardAnswers}
          {...(compact ? { compact: true, error: errors.answers ?? null, errorKey: errors.answersKey ?? null } : {})} />}
        {compact && !choiceTypes ? (
          // The answers' error sits under them; Done focuses their first field (`data-field-invalid`).
          <div {...(answersErr ? { "data-field-invalid": "" } : {})} className="space-y-1.5">
            {typeFields}
            {answersErr && <p className="text-sm text-red-700">{answersErr}</p>}
          </div>
        ) : typeFields}
        <RichTextField label={t("bank.editor.explanation")} rows={3} value={form.explanation} disabled={disabled} onChange={(v) => patch({ explanation: v })}
          {...(compact ? { smartPreview: true, toolbarOnFocus: true, error: err("explanation") } : {})} />
        {err("other") && <p className="text-sm text-red-700">{err("other")}</p>}
      </div>

      {showMeta && (
        <div className={`${cardCls} grid gap-3 sm:grid-cols-2`}>
          <div>
            <label className={labelCls} htmlFor={id("section")}>{t("bank.editor.section")}</label>
            <input id={id("section")} list={id("sections")} className={inputCls} disabled={disabled} maxLength={40} value={form.section}
              onChange={(e) => patch({ section: e.target.value })} />
            <datalist id={id("sections")}>
              {ORT_SECTIONS.map((s) => <option key={s} value={s}>{t(`sections.${s}`)}</option>)}
            </datalist>
          </div>
          <div>
            <label className={labelCls} htmlFor={id("topic")}>{t("bank.editor.topic")}</label>
            <input id={id("topic")} className={inputCls} disabled={disabled} maxLength={200} value={form.topic} onChange={(e) => patch({ topic: e.target.value })} />
          </div>
          <div>
            <label className={labelCls} htmlFor={id("diff")}>{t("bank.editor.difficulty")}</label>
            <select id={id("diff")} className={inputCls} disabled={disabled} value={form.difficulty} onChange={(e) => patch({ difficulty: e.target.value as QuestionForm["difficulty"] })}>
              <option value="">{t("bank.editor.none")}</option>
              {DIFFICULTIES.map((d) => <option key={d} value={d}>{t(`bank.difficulty.${d}`)}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor={id("tags")}>{t("bank.editor.tags")}</label>
            <input id={id("tags")} className={inputCls} disabled={disabled} value={form.tags} onChange={(e) => patch({ tags: e.target.value })} />
            <p className="mt-0.5 text-xs text-slate-500">{t("bank.editor.tagsHint")}</p>
          </div>
          <div className="sm:col-span-2">
            <label className={labelCls} htmlFor={id("passage")}>{t("bank.editor.passage")}</label>
            <select id={id("passage")} className={inputCls} disabled={disabled} value={form.passageId} onChange={(e) => patch({ passageId: e.target.value })}>
              <option value="">{t("bank.editor.noPassage")}</option>
              {passages.map((p) => (
                <option key={p.id} value={p.id}>
                  {`[${t(`courses.languages.${p.language}`)}] ${p.title || p.body_excerpt.slice(0, 60)}`}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
    </>
  );
}
