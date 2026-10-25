"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { getQuestion, previewQuestion } from "@/lib/lms/content";
import type { QuestionStaffOut, StudentQuestionOut } from "@/lib/lms/contentTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { ConflictDialog } from "@/components/lms/content/ConflictDialog";
import { ContentError } from "@/components/lms/content/ContentError";
import { QuestionEditor } from "@/components/lms/content/QuestionEditor";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { StudentPreview } from "@/components/lms/content/StudentPreview";
import { TranslationPanel } from "@/components/lms/content/TranslationPanel";
import { VersionHistory } from "@/components/lms/content/VersionHistory";

type Tab = "edit" | "preview" | "history" | "translations";
const TABS: Tab[] = ["edit", "preview", "history", "translations"];

export default function QuestionPage() {
  const { lang, t } = useTranslation();
  const { questionId } = useParams<{ questionId: string }>();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const [q, setQ] = useState<QuestionStaffOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tab, setTab] = useState<Tab>("edit");
  const [status, setStatus] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [preview, setPreview] = useState<StudentQuestionOut | null>(null);
  const [previewError, setPreviewError] = useState<unknown>(null);

  const load = useCallback(async () => {
    try {
      setQ(await getQuestion(course.id, questionId));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [course.id, questionId]);
  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (tab !== "preview" || !q) return;
    let alive = true;
    setPreview(null);
    setPreviewError(null);
    previewQuestion(course.id, q.id, q.current_version.id).then((p) => { if (alive) setPreview(p); }).catch((e) => { if (alive) setPreviewError(e); });
    return () => { alive = false; };
  }, [tab, q?.id, q?.current_version.id, course.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const reloadFromConflict = async () => {
    setConflict(false);
    setStatus(null);
    await load();
  };

  const base = `/${lang}/courses/${course.id}/bank`;
  if (error && !q) return <ContentError error={error} onRetry={load} />;
  if (!q) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;
  const deleted = !!q.deleted_at;
  const editable = canEdit && !deleted;

  return (
    <div className="space-y-4">
      <Link href={`${base}/${q.bank_id}`} className="text-sm font-medium text-brand-700 hover:underline">{t("bank.backToQuestions")}</Link>
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-bold text-slate-900">{t("bank.editor.title", { n: q.version_no })}</h2>
        {deleted && <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-800">{t("bank.list.deletedBadge")}</span>}
      </div>
      {/* Phase 6 S8: the tab row wraps at 375 px instead of widening the page. */}
      <div role="tablist" aria-label={t("bank.editor.tabsLabel")} className="flex flex-wrap gap-x-1 border-b border-slate-200">
        {TABS.map((id) => (
          <button key={id} role="tab" type="button" aria-selected={tab === id} onClick={() => setTab(id)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-semibold ${tab === id ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
            {t(`bank.editor.tabs.${id}`)}
          </button>
        ))}
      </div>
      {status && <p role="status" className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{status}</p>}

      {tab === "edit" && (
        <QuestionEditor courseId={course.id} bankId={q.bank_id} courseLanguages={course.languages} defaultLanguage={course.default_language}
          question={q} readOnly={!editable}
          onSaved={(saved, unchanged) => { setQ(saved); setStatus(unchanged ? t("bank.editor.unchanged") : t("bank.editor.saved")); }}
          onConflict={() => setConflict(true)} />
      )}
      {tab === "preview" && (
        <div>
          <ContentError error={previewError} />
          {!preview && !previewError && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
          {preview && <StudentPreview q={preview} />}
        </div>
      )}
      {tab === "history" && (
        <VersionHistory courseId={course.id} question={q} canEdit={editable}
          onReverted={(r) => { setQ(r); setStatus(t("bank.history.reverted")); setTab("edit"); }}
          onConflict={() => setConflict(true)} />
      )}
      {tab === "translations" && (
        <TranslationPanel courseId={course.id} question={q} courseLanguages={course.languages} canEdit={editable} onChanged={load} />
      )}
      <ConflictDialog open={conflict} onReload={() => void reloadFromConflict()} onClose={() => setConflict(false)} />
    </div>
  );
}
