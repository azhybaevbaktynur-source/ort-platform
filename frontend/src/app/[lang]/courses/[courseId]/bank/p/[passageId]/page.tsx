"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { getPassage } from "@/lib/lms/content";
import type { PassageOut } from "@/lib/lms/contentTypes";
import { EmptyState, LoadingState, PageHeader, TabPanel, Tabs, toast } from "@/components/ui";
import { useTabCrumbs } from "@/components/lms/course/StaffCourseUi";
import { useCourse } from "@/components/lms/CourseContext";
import { ConflictDialog } from "@/components/lms/content/ConflictDialog";
import { ContentError } from "@/components/lms/content/ContentError";
import { PassageEditor, PassageHistory } from "@/components/lms/content/PassageEditor";
import { useCanEditContent } from "@/components/lms/content/StaffGate";

type Tab = "edit" | "questions" | "history";

export default function PassagePage() {
  const { lang, t } = useTranslation();
  const { passageId } = useParams<{ passageId: string }>();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const [p, setP] = useState<PassageOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tab, setTab] = useState<Tab>("edit");
  const [conflict, setConflict] = useState(false);

  const load = useCallback(async () => {
    try { setP(await getPassage(course.id, passageId)); setError(null); } catch (e) { setError(e); }
  }, [course.id, passageId]);
  useEffect(() => { void load(); }, [load]);

  const base = `/${lang}/courses/${course.id}/bank`;
  const bankId = p ? p.bank_id || p.questions[0]?.bank_id : undefined;
  const crumbs = useTabCrumbs("bank", [
    { label: t("bank.passages.back"), href: bankId ? `${base}/${bankId}/passages` : base },
    { label: p?.current_version.title || t("bank.passages.untitled") },
  ], course.id);
  if (error && !p) return <ContentError error={error} onRetry={load} />;
  if (!p) return <LoadingState rows={2} />;
  const editable = canEdit && !p.deleted_at;
  const setStatus = (msg: string | null) => { if (msg) toast.success(msg); }; // Phase 6b S5c: confirmations are toasts

  return (
    <div className="space-y-4">
      <PageHeader breadcrumbs={crumbs} title={p.current_version.title || t("bank.passages.untitled")} className="mb-2" />
      {/* Phase 6b S5c: design-system Tabs (one scrollable row at 375 px). */}
      <Tabs id="passage-editor" label={t("bank.editor.tabsLabel")} value={tab} onChange={(v) => setTab(v as Tab)}
        items={(["edit", "questions", "history"] as Tab[]).map((id) => ({ id, label: t(`bank.passages.tabs.${id}`) }))} />
      <TabPanel tabsId="passage-editor" value={tab} className="pt-0">
      {tab === "edit" && (
        <PassageEditor courseId={course.id} bankId={bankId || ""} passage={p} courseLanguages={course.languages} defaultLanguage={course.default_language}
          readOnly={!editable} onSaved={(np) => { setP(np); setStatus(t("bank.editor.saved")); }} onConflict={() => setConflict(true)} />
      )}
      {tab === "questions" && (
        p.questions.length === 0 ? <EmptyState title={t("bank.passages.noQuestions")} /> : (
          <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
            {p.questions.map((q) => (
              <li key={q.id} className="px-4 py-3 text-sm">
                <Link href={`${base}/q/${q.id}`} className="font-medium text-brand-700 hover:underline">{q.stem_excerpt || t("bank.questions.noStem")}</Link>
              </li>
            ))}
          </ul>
        )
      )}
      {tab === "history" && (
        <PassageHistory courseId={course.id} passage={p} canEdit={editable}
          onReverted={(np) => { setP(np); setStatus(t("bank.history.reverted")); setTab("edit"); }} onConflict={() => setConflict(true)} />
      )}
      </TabPanel>
      <ConflictDialog open={conflict} onReload={() => { setConflict(false); setStatus(null); void load(); }} onClose={() => setConflict(false)} />
    </div>
  );
}
