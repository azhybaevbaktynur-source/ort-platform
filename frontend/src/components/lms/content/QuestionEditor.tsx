"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { createQuestion, listPassages, updateQuestion } from "@/lib/lms/content";
import {
  QUESTION_TYPES, type PassageSummaryOut, type QuestionStaffOut, type QuestionType,
} from "@/lib/lms/contentTypes";
import type { Lang } from "@/lib/lms/types";
import { ContentError } from "./ContentError";
import { QuestionCardForm } from "./QuestionCardForm";
import {
  contentFromForm, emptyForm, formFromStaff, metaFromForm, validateForm, type QuestionForm,
} from "./types/formModel";
import { btnPrimary } from "@/components/lms/course/staffUi"; // Phase 6b S5c

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

  return (
    <form onSubmit={save} className="space-y-5">
      {/* Phase 7c S3 (PHASE_7C_DESIGN 8.4): the form body lives in QuestionCardForm (same markup), shared with the quiz editor. */}
      <QuestionCardForm form={form} onChange={patch} disabled={disabled} courseId={courseId} languages={courseLanguages}
        typeOptions={QUESTION_TYPES} lockType={editing} lockLanguage={editing} passages={passages} />

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
