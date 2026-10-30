"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { getBank, getQuestion, previewQuestion } from "@/lib/lms/content";
import type { BankOut, QuestionStaffOut, StudentQuestionOut } from "@/lib/lms/contentTypes";
import { Badge, LoadingState, PageHeader, TabPanel, Tabs, toast } from "@/components/ui";
import { useTabCrumbs } from "@/components/lms/course/StaffCourseUi";
import { useCourse } from "@/components/lms/CourseContext";
import { ConflictDialog } from "@/components/lms/content/ConflictDialog";
import { ContentError } from "@/components/lms/content/ContentError";
import { QuestionEditor } from "@/components/lms/content/QuestionEditor";
import { useCanEditBank } from "@/components/lms/content/StaffGate";
import { StudentPreview } from "@/components/lms/content/StudentPreview";
import { TranslationPanel } from "@/components/lms/content/TranslationPanel";
import { VersionHistory } from "@/components/lms/content/VersionHistory";

type Tab = "edit" | "preview" | "history" | "translations";
const TABS: Tab[] = ["edit", "preview", "history", "translations"];

export default function QuestionPage() {
  const { lang, t } = useTranslation();
  const { questionId } = useParams<{ questionId: string }>();
  const { course } = useCourse();
  const [q, setQ] = useState<QuestionStaffOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tab, setTab] = useState<Tab>("edit");
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
  // Phase 6b S5c: the bank title for the breadcrumbs (Question bank > bank > question).
  const [bank, setBank] = useState<BankOut | null>(null);
  const bankId = q?.bank_id;
  useEffect(() => {
    if (!bankId) return;
    getBank(course.id, bankId).then(setBank).catch(() => setBank(null));
  }, [course.id, bankId]);
  const canEdit = useCanEditBank(bank); // Phase 9 S2: `bank.can_edit` (org admins on shared banks)
  const base = `/${lang}/courses/${course.id}/bank`;
  const crumbs = useTabCrumbs("bank", [
    { label: bank?.title || t("bank.backToQuestions"), href: bankId ? `${base}/${bankId}` : base },
    { label: q ? t("bank.editor.title", { n: q.version_no }) : t("lms.common.loading") },
  ], course.id);

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
    await load();
  };

  if (error && !q) return <ContentError error={error} onRetry={load} />;
  if (!q) return <LoadingState rows={2} />;
  const deleted = !!q.deleted_at;
  const editable = canEdit && !deleted;
  const setStatus = (msg: string) => toast.success(msg); // Phase 6b S5c: saved / reverted confirmations are toasts

  return (
    <div className="space-y-4">
      <PageHeader breadcrumbs={crumbs} title={t("bank.editor.title", { n: q.version_no })}
        badge={deleted ? <Badge tone="danger">{t("bank.list.deletedBadge")}</Badge> : undefined} className="mb-2" />
      {/* Phase 6b S5c: design-system Tabs: one scrollable row at 375 px, arrow keys move between tabs. */}
      <Tabs id="question-editor" label={t("bank.editor.tabsLabel")} value={tab} onChange={(v) => setTab(v as Tab)}
        items={TABS.map((id) => ({ id, label: t(`bank.editor.tabs.${id}`) }))} />
      <TabPanel tabsId="question-editor" value={tab} className="pt-0">
      {tab === "edit" && (
        <QuestionEditor courseId={course.id} bankId={q.bank_id} courseLanguages={course.languages} defaultLanguage={course.default_language}
          question={q} readOnly={!editable}
          onSaved={(saved, unchanged) => { setQ(saved); setStatus(unchanged ? t("bank.editor.unchanged") : t("bank.editor.saved")); }}
          onConflict={() => setConflict(true)} />
      )}
      {tab === "preview" && (
        <div>
          <ContentError error={previewError} />
          {!preview && !previewError && <LoadingState rows={1} />}
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
      </TabPanel>
      <ConflictDialog open={conflict} onReload={() => void reloadFromConflict()} onClose={() => setConflict(false)} />
    </div>
  );
}
