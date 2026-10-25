"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { addSection, deleteSection, getAssessment, reorderSections, updateSection } from "@/lib/lms/assessments";
import { isStaffAssessment, type AssessmentStaffOut, type SectionIn, type SectionOut } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { isAssessmentLocked, useTemplateUi } from "@/lib/lms/templates";
import { useCourse } from "@/components/lms/CourseContext";
import { StaffGate, useCanEditContent } from "@/components/lms/content/StaffGate";
import { useTabCrumbs } from "@/components/lms/course/StaffCourseUi"; // Phase 6b S5c
import { Button, ConfirmDialog, EmptyState, LoadingState, PageHeader } from "@/components/ui";
import { AddItemsDialog } from "@/components/lms/assessments/AddItemsDialog";
import { AssessmentError } from "@/components/lms/assessments/AssessmentError";
import type { RowCtx } from "@/components/lms/assessments/ItemRow";
import { PublishPanel } from "@/components/lms/assessments/PublishPanel";
import { SectionCard, sectionName } from "@/components/lms/assessments/SectionCard";
import { SectionDialog } from "@/components/lms/assessments/SectionDialog";
import { SettingsPanel } from "@/components/lms/assessments/SettingsPanel";
import { moveIndex } from "@/components/lms/assessments/format";
import { useDragReorder } from "@/components/lms/assessments/useDragReorder";

export default function AssessmentEditPage() {
  return <StaffGate><Builder /></StaffGate>;
}

function Builder() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const params = useParams<{ assessmentId: string }>();
  const router = useRouter();
  const canEdit = useCanEditContent();
  const ui = useTemplateUi(); // Phase 6 S4b
  const aid = params.assessmentId;
  const base = `/${lang}/courses/${course.id}/assessments`;
  const [a, setA] = useState<AssessmentStaffOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [sectionDlg, setSectionDlg] = useState<{ section: SectionOut | null } | null>(null);
  const [secBusy, setSecBusy] = useState(false);
  const [secError, setSecError] = useState<unknown>(null);
  const [toDelete, setToDelete] = useState<SectionOut | null>(null);
  const [addTo, setAddTo] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const out = await getAssessment(course.id, aid);
      if (!isStaffAssessment(out)) { router.replace(`${base}/${aid}`); return; }
      setA(out);
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [course.id, aid, base, router]);
  useEffect(() => { void load(); }, [load]);

  const reorder = useCallback(async (ids: string[]) => {
    setActionError(null);
    try { await reorderSections(course.id, aid, ids); } catch (e) { setActionError(e); }
    await load();
  }, [course.id, aid, load]);
  const sectionIds = a?.sections.map((s) => s.id) ?? [];
  const moveSection = (from: number, to: number) => void reorder(moveIndex(sectionIds, from, to));
  // --- Phase 6 S4b: a locked course template fixes the sections (add, delete, reorder), design §5.4 ---
  const structureLocked = !!a && isAssessmentLocked(ui, a.preset);
  const drag = useDragReorder(moveSection, canEdit && !structureLocked);
  const aTitle = a ? pickLocalized(a.title, lang, course.default_language) || t("assessments.untitled") : "";
  const crumbs = useTabCrumbs("assessments", [
    { label: aTitle || t("lms.common.loading"), href: `${base}/${aid}` },
    { label: t("teaching.builderCrumb") },
  ], course.id);

  if (error && !a) return <AssessmentError error={error} onRetry={() => void load()} />;
  if (!a) return <LoadingState rows={3} />;

  const ctx: RowCtx = {
    courseId: course.id, assessmentId: a.id, canEdit, sections: a.sections, currentSectionId: "",
    onChanged: load, onError: setActionError,
  };

  const submitSection = async (v: SectionIn) => {
    setSecBusy(true);
    setSecError(null);
    try {
      if (sectionDlg?.section) await updateSection(course.id, a.id, sectionDlg.section.id, v);
      else await addSection(course.id, a.id, v);
      setSectionDlg(null);
      await load();
    } catch (e) {
      setSecError(e);
    } finally {
      setSecBusy(false);
    }
  };
  const removeSection = async () => {
    if (!toDelete) return;
    setSecBusy(true);
    setSecError(null);
    try {
      await deleteSection(course.id, a.id, toDelete.id);
      setToDelete(null);
      await load();
    } catch (e) {
      setSecError(e);
    } finally {
      setSecBusy(false);
    }
  };

  const title = aTitle;
  const addSectionBtn = canEdit ? (
    <Button variant="secondary" disabled={structureLocked} title={structureLocked ? t("templates.lockedNote") : undefined}
      onClick={() => { setSecError(null); setSectionDlg({ section: null }); }}>{t("assessments.section.add")}</Button>
  ) : undefined;
  return (
    <div className="space-y-4">
      {/* Phase 6b S5c: PageHeader with breadcrumbs; the one primary of the page is "Publish" in the publish panel (UX T8). */}
      <PageHeader breadcrumbs={crumbs} title={t("assessments.builder.title", { title })} className="mb-2" />
      {!canEdit && <p className="rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2 text-sm text-amber-900">{t("assessments.builder.readOnly")}</p>}
      <PublishPanel assessment={a} courseId={course.id} canEdit={canEdit} onChanged={load} />
      <details className="rounded-2xl">
        <summary className="cursor-pointer rounded-xl px-1 py-2 text-sm font-semibold text-slate-800">{t("assessments.builder.settings")}</summary>
        <div className="mt-2">
          <SettingsPanel assessment={a} courseId={course.id} courseLanguages={course.languages} defaultLanguage={course.default_language}
            disabled={!canEdit} onSaved={load} onConflict={load} />
        </div>
      </details>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-900">{t("assessments.builder.sections")}</h2>
        {addSectionBtn}
      </div>
      {canEdit && structureLocked && <p role="note" className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{t("templates.lockedNote")}</p>}
      <AssessmentError error={actionError} />
      {a.sections.length === 0 && <EmptyState title={t("assessments.builder.noSections")} action={addSectionBtn} />}
      <div className="space-y-4">
        {a.sections.map((s, i) => (
          <SectionCard key={s.id} section={s} assessment={a} ctx={ctx} index={i} count={a.sections.length} defaultLanguage={course.default_language}
            dragProps={drag(i)} onMoveBy={(d) => moveSection(i, i + d)} structureLocked={structureLocked}
            onEdit={() => { setSecError(null); setSectionDlg({ section: s }); }}
            onDelete={() => { setSecError(null); setToDelete(s); }} onAdd={() => setAddTo(s.id)} />
        ))}
      </div>
      <SectionDialog open={!!sectionDlg} section={sectionDlg?.section ?? null} assessment={a} languages={a.languages} defaultLanguage={a.languages.includes(course.default_language) ? course.default_language : a.languages[0]}
        busy={secBusy} error={secError} onSubmit={(v) => void submitSection(v)} onCancel={() => setSectionDlg(null)} />
      <ConfirmDialog open={!!toDelete} tone="danger" busy={secBusy} title={t("assessments.section.deleteTitle")}
        object={toDelete ? sectionName(toDelete, lang, course.default_language, t) : undefined}
        effect={t("assessments.section.deleteBody", { name: toDelete ? sectionName(toDelete, lang, course.default_language, t) : "" })}
        confirmLabel={t("assessments.section.delete")} onConfirm={() => void removeSection()} onCancel={() => setToDelete(null)}
        error={secError ? <AssessmentError error={secError} /> : undefined} />
      {addTo && (
        <AddItemsDialog open courseId={course.id} assessmentId={a.id} sectionId={addTo} onClose={() => setAddTo(null)} onAdded={load} />
      )}
    </div>
  );
}
