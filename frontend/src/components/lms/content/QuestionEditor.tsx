"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { createQuestion, listPassages, updateQuestion } from "@/lib/lms/content";
import {
  DIFFICULTIES, ORT_SECTIONS, type PassageSummaryOut, type QuestionStaffOut, type QuestionType,
} from "@/lib/lms/contentTypes";
import type { Lang } from "@/lib/lms/types";
import { ContentError } from "./ContentError";
import { ImagePicker } from "./ImagePicker";
import { RichTextField } from "./RichTextField";
import { ChoiceFields } from "./types/ChoiceFields";
import { ComparisonFields, EssayFields, NumericFields, ShortTextFields, TrueFalseFields } from "./types/SimpleFields";
import {
  contentFromForm, emptyForm, formFromStaff, metaFromForm, validateForm, type QuestionForm,
} from "./types/formModel";
import { btnPrimary, cardCls, inputCls, labelCls } from "./ui";

/** Create / edit form for one question. Save sends base_version_id; the page handles conflicts. */
export function QuestionEditor({
  courseId, bankId, courseLanguages, defaultLanguage, question, createType, readOnly, onSaved, onConflict,
}: {
  courseId: string;
  bankId: string;
  courseLanguages: Lang[];
  defaultLanguage: Lang;
  question?: QuestionStaffOut;
  createType?: QuestionType;
  readOnly?: boolean;
  onSaved: (q: QuestionStaffOut, unchanged: boolean) => void;
  onConflict: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<QuestionForm>(() =>
    question ? formFromStaff(question) : emptyForm(createType || "single_choice", defaultLanguage));
  const [passages, setPassages] = useState<PassageSummaryOut[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [clientError, setClientError] = useState<string | null>(null);
  const editing = !!question;
  const baseVersionId = question?.current_version.id;

  // Re-seed the form when a different version becomes current (after reload or revert).
  useEffect(() => {
    if (question) setForm(formFromStaff(question));
  }, [question?.id, baseVersionId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let alive = true;
    listPassages(courseId, bankId, { limit: 100 }).then((p) => { if (alive) setPassages(p.items); }).catch(() => {});
    return () => { alive = false; };
  }, [courseId, bankId]);

  const patch = (p: Partial<QuestionForm>) => setForm((f) => ({ ...f, ...p }));
  const disabled = saving || !!readOnly;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const bad = validateForm(form);
    setClientError(bad);
    if (bad) return;
    setSaving(true);
    setError(null);
    try {
      if (editing && question) {
        const q = await updateQuestion(courseId, question.id, {
          base_version_id: question.current_version.id,
          content: contentFromForm(form),
          meta: metaFromForm(form),
        });
        onSaved(q, !!q.unchanged);
      } else {
        const q = await createQuestion(courseId, bankId, { ...contentFromForm(form), ...metaFromForm(form), language: form.language });
        onSaved(q, false);
      }
    } catch (err) {
      if ((err as { code?: string }).code === "version_conflict") onConflict();
      else setError(err);
    } finally {
      setSaving(false);
    }
  };

  const fieldProps = { form, onChange: patch, disabled };
  return (
    <form onSubmit={save} className="space-y-5">
      <div className={`${cardCls} grid gap-3 sm:grid-cols-3`}>
        <div>
          <span className={labelCls}>{t("bank.editor.type")}</span>
          {editing ? (
            <p className="py-2 text-sm font-semibold text-slate-900">{t(`bank.types.${form.type}.name`)}</p>
          ) : (
            <select className={inputCls} disabled={disabled} value={form.type} onChange={(e) => patch({ type: e.target.value as QuestionType })}>
              {(["single_choice", "multiple_answers", "true_false", "comparison", "numeric", "short_text", "essay"] as QuestionType[]).map((ty) => (
                <option key={ty} value={ty}>{t(`bank.types.${ty}.name`)}</option>
              ))}
            </select>
          )}
        </div>
        <div>
          <label className={labelCls} htmlFor="q-lang">{t("bank.editor.language")}</label>
          {editing ? (
            <p className="py-2 text-sm font-semibold text-slate-900">{t(`courses.languages.${form.language}`)}</p>
          ) : (
            <select id="q-lang" className={inputCls} disabled={disabled} value={form.language} onChange={(e) => patch({ language: e.target.value as Lang })}>
              {courseLanguages.map((l) => <option key={l} value={l}>{t(`courses.languages.${l}`)}</option>)}
            </select>
          )}
        </div>
        <div>
          <label className={labelCls} htmlFor="q-points">{t("bank.editor.points")}</label>
          <input id="q-points" type="number" min={0} max={1000} step="0.01" className={inputCls} disabled={disabled} value={form.points}
            onChange={(e) => patch({ points: e.target.value })} />
        </div>
      </div>

      <div className={`${cardCls} space-y-4`}>
        <p className="text-xs text-slate-500">{t(`bank.types.${form.type}.hint`)}</p>
        <RichTextField label={t("bank.editor.stem")} rows={5} value={form.stem} disabled={disabled} onChange={(v) => patch({ stem: v })} />
        <ImagePicker courseId={courseId} label={t("bank.editor.image")} value={form.image} disabled={disabled} onChange={(img) => patch({ image: img })} />
        {(form.type === "single_choice" || form.type === "multiple_answers") && <ChoiceFields courseId={courseId} {...fieldProps} />}
        {form.type === "true_false" && <TrueFalseFields {...fieldProps} />}
        {form.type === "comparison" && <ComparisonFields {...fieldProps} />}
        {form.type === "numeric" && <NumericFields {...fieldProps} />}
        {form.type === "short_text" && <ShortTextFields {...fieldProps} />}
        {form.type === "essay" && <EssayFields {...fieldProps} />}
        <RichTextField label={t("bank.editor.explanation")} rows={3} value={form.explanation} disabled={disabled} onChange={(v) => patch({ explanation: v })} />
      </div>

      <div className={`${cardCls} grid gap-3 sm:grid-cols-2`}>
        <div>
          <label className={labelCls} htmlFor="q-section">{t("bank.editor.section")}</label>
          <input id="q-section" list="q-sections" className={inputCls} disabled={disabled} maxLength={40} value={form.section}
            onChange={(e) => patch({ section: e.target.value })} />
          <datalist id="q-sections">
            {ORT_SECTIONS.map((s) => <option key={s} value={s}>{t(`sections.${s}`)}</option>)}
          </datalist>
        </div>
        <div>
          <label className={labelCls} htmlFor="q-topic">{t("bank.editor.topic")}</label>
          <input id="q-topic" className={inputCls} disabled={disabled} maxLength={200} value={form.topic} onChange={(e) => patch({ topic: e.target.value })} />
        </div>
        <div>
          <label className={labelCls} htmlFor="q-diff">{t("bank.editor.difficulty")}</label>
          <select id="q-diff" className={inputCls} disabled={disabled} value={form.difficulty} onChange={(e) => patch({ difficulty: e.target.value as QuestionForm["difficulty"] })}>
            <option value="">{t("bank.editor.none")}</option>
            {DIFFICULTIES.map((d) => <option key={d} value={d}>{t(`bank.difficulty.${d}`)}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls} htmlFor="q-tags">{t("bank.editor.tags")}</label>
          <input id="q-tags" className={inputCls} disabled={disabled} value={form.tags} onChange={(e) => patch({ tags: e.target.value })} />
          <p className="mt-0.5 text-xs text-slate-500">{t("bank.editor.tagsHint")}</p>
        </div>
        <div className="sm:col-span-2">
          <label className={labelCls} htmlFor="q-passage">{t("bank.editor.passage")}</label>
          <select id="q-passage" className={inputCls} disabled={disabled} value={form.passageId} onChange={(e) => patch({ passageId: e.target.value })}>
            <option value="">{t("bank.editor.noPassage")}</option>
            {passages.map((p) => (
              <option key={p.id} value={p.id}>
                {`[${t(`courses.languages.${p.language}`)}] ${p.title || p.body_excerpt.slice(0, 60)}`}
              </option>
            ))}
          </select>
        </div>
      </div>

      {clientError && <p role="alert" className="text-sm text-red-700">{t(clientError)}</p>}
      <ContentError error={error} />
      {!readOnly && (
        <div className="flex justify-end">
          <button type="submit" disabled={saving} className={btnPrimary}>
            {saving ? t("bank.editor.saving") : editing ? t("lms.common.save") : t("bank.editor.create")}
          </button>
        </div>
      )}
    </form>
  );
}
