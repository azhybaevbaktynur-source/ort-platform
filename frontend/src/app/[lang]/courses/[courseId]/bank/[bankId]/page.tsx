"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { deleteQuestion, getBank, listQuestions, moveQuestion, restoreQuestion } from "@/lib/lms/content";
import { QUESTION_TYPES, type BankOut, type QuestionSummaryOut, type QuestionType } from "@/lib/lms/contentTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { Pager } from "@/components/lms/Pager";
import { BankFilters, EMPTY_FILTERS, type BankFilterState } from "@/components/lms/content/BankFilters";
import { BankHeader } from "@/components/lms/content/BankHeader";
import { ContentError } from "@/components/lms/content/ContentError";
import { QuestionRow } from "@/components/lms/content/QuestionRow";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { inputCls } from "@/components/lms/content/ui";
import { ConfirmDialog, EmptyState, LoadingState } from "@/components/ui";
import { MathRenderer } from "@/components/math/MathRenderer";

export default function BankQuestionsPage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { bankId } = useParams<{ bankId: string }>();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const [bank, setBank] = useState<BankOut | null>(null);
  const [filters, setFilters] = useState<BankFilterState>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<BankFilterState>(EMPTY_FILTERS);
  const [items, setItems] = useState<QuestionSummaryOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [rowBusy, setRowBusy] = useState(false);
  const [toDelete, setToDelete] = useState<QuestionSummaryOut | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);

  // Debounce filters (300 ms) before hitting the API.
  useEffect(() => {
    const id = setTimeout(() => setApplied(filters), 300);
    return () => clearTimeout(id);
  }, [filters]);

  useEffect(() => {
    getBank(course.id, bankId).then(setBank).catch(setError);
  }, [course.id, bankId]);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listQuestions(course.id, bankId, {
        q: applied.q, type: applied.type, language: applied.language, section: applied.section, topic: applied.topic,
        difficulty: applied.difficulty, tag: applied.tag, deleted: applied.deleted || undefined, cursor: next, limit: 50,
      });
      setItems((p) => (next ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id, bankId, applied]);
  useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setRowBusy(true);
    setActionError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setActionError(e);
    } finally {
      setRowBusy(false);
      setToDelete(null);
    }
  };

  const newQuestion = (type: QuestionType) => router.push(`/${lang}/courses/${course.id}/bank/${bankId}/new?type=${type}`);

  return (
    <div className="space-y-4">
      <BankHeader courseId={course.id} bank={bank} active="questions" />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <BankFilters value={filters} onChange={setFilters} />
      </div>
      {canEdit && (
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-700" htmlFor="new-type">{t("bank.questions.new")}</label>
          <select id="new-type" className={`${inputCls} w-auto`} value="" onChange={(e) => e.target.value && newQuestion(e.target.value as QuestionType)}>
            <option value="">{t("bank.questions.pickType")}</option>
            {QUESTION_TYPES.map((ty) => <option key={ty} value={ty}>{t(`bank.types.${ty}.name`)}</option>)}
          </select>
        </div>
      )}
      <ContentError error={error || actionError} onRetry={error ? () => load() : undefined} />
      {loading && items.length === 0 && !error && <LoadingState rows={3} />}
      {!loading && !error && items.length === 0 && <EmptyState title={t("bank.questions.empty")} />}
      {items.length > 0 && (
        <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
          {items.map((q) => (
            <QuestionRow key={q.id} courseId={course.id} q={q} busy={rowBusy} canEdit={canEdit}
              onMove={(d) => void act(() => moveQuestion(course.id, q.id, d))}
              onDelete={() => setToDelete(q)}
              onRestore={() => void act(() => restoreQuestion(course.id, q.id))} />
          ))}
        </ul>
      )}
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
      <ConfirmDialog open={!!toDelete} tone="danger" busy={rowBusy} title={t("bank.questions.deleteTitle")}
        object={toDelete ? (toDelete.stem_excerpt ? <MathRenderer content={toDelete.stem_excerpt} className="!text-sm line-clamp-3" /> : t("bank.questions.noStem")) : undefined}
        effect={t("bank.questions.deleteBody")}
        confirmLabel={t("bank.questions.delete")} onConfirm={() => toDelete && void act(() => deleteQuestion(course.id, toDelete.id))}
        onCancel={() => setToDelete(null)} />
    </div>
  );
}
