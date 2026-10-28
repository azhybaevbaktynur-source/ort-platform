"use client";

import React from "react";
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

/**
 * Phase 7c S3 (PHASE_7C_DESIGN 8.4): the body of the question form (type, language, points, stem, image, per-type
 * fields, explanation, meta grid), extracted from `QuestionEditor` without any change to its markup, so the Bank tab
 * (and the ORT bank screens) render exactly as before. The quiz editor card renders it with its own options.
 */
export function QuestionCardForm({
  form, onChange, disabled, courseId, languages, typeOptions = QUESTION_TYPES, lockType = false, lockLanguage = false,
  passages = [], showMeta = true, idPrefix = "q", keyboardAnswers = false,
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
}) {
  const { t } = useTranslation();
  const patch = onChange;
  const fieldProps = { form, onChange: patch, disabled };
  const id = (s: string) => `${idPrefix}-${s}`;
  return (
    <>
      <div className={`${cardCls} grid gap-3 sm:grid-cols-3`}>
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
        <div>
          <label className={labelCls} htmlFor={id("points")}>{t("bank.editor.points")}</label>
          <input id={id("points")} type="number" min={0} max={1000} step="0.01" className={inputCls} disabled={disabled} value={form.points}
            onChange={(e) => patch({ points: e.target.value })} />
        </div>
      </div>

      <div className={`${cardCls} space-y-4`}>
        <p className="text-xs text-slate-500">{t(`bank.types.${form.type}.hint`)}</p>
        <RichTextField label={t("bank.editor.stem")} rows={5} value={form.stem} disabled={disabled} onChange={(v) => patch({ stem: v })} />
        <ImagePicker courseId={courseId} label={t("bank.editor.image")} value={form.image} disabled={disabled} onChange={(img) => patch({ image: img })} />
        {(form.type === "single_choice" || form.type === "multiple_answers") && <ChoiceFields courseId={courseId} {...fieldProps} keyboardAnswers={keyboardAnswers} />}
        {form.type === "true_false" && <TrueFalseFields {...fieldProps} />}
        {form.type === "comparison" && <ComparisonFields {...fieldProps} />}
        {form.type === "numeric" && <NumericFields {...fieldProps} />}
        {form.type === "short_text" && <ShortTextFields {...fieldProps} />}
        {form.type === "essay" && <EssayFields {...fieldProps} />}
        <RichTextField label={t("bank.editor.explanation")} rows={3} value={form.explanation} disabled={disabled} onChange={(v) => patch({ explanation: v })} />
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
