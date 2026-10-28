"use client";

import React, { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { addSection, deleteSection, getAssessment, reorderSections, updateSection } from "@/lib/lms/assessments";
import { isStaffAssessment, type AssessmentStaffOut, type SectionIn, type SectionOut } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { isAssessmentLocked, useTemplateUi } from "@/lib/lms/templates";
import { templateLockedFields } from "@/lib/lms/assessmentTypes"; // Phase 7b S5
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { useTabCrumbs } from "@/components/lms/course/StaffCourseUi"; // Phase 6b S5c
import { Button, ConfirmDialog, EmptyState, LoadingState, PageHeader } from "@/components/ui";
import { AddItemsDialog } from "./AddItemsDialog";
import { AssessmentError } from "./AssessmentError";
import type { RowCtx } from "./ItemRow";
import { PublishPanel } from "./PublishPanel";
import { SectionCard, sectionName } from "./SectionCard";
import { SectionDialog } from "./SectionDialog";
import { SettingsPanel } from "./SettingsPanel";
import { moveIndex } from "./format";
import { useDragReorder } from "./useDragReorder";

/**
 * Phase 7c S3 (PHASE_7C_DESIGN 8.1): the section builder, moved verbatim from `edit/page.tsx` (same markup, classes
 * and i18n keys) so preset exams (ORT) keep it pixel for pixel. `EditorSwitch` loads the assessment once and passes it.
 */
export function SectionBuilder({ initial }: { initial: AssessmentStaffOut }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const canEdit = useCanEditContent();
  const ui = useTemplateUi(); // Phase 6 S4b
  const aid = initial.id;
  const base = `/${lang}/courses/${course.id}/assessments`;
  const [a, setA] = useState<AssessmentStaffOut | null>(initial);
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

  const reorder = useCallback(async (ids: string[]) => {
    setActionError(null);
    try { await reorderSections(course.id, aid, ids); } catch (e) { setActionError(e); }
    await load();
  }, [course.id, aid, load]);
  const sectionIds = a?.sections.map((s) => s.id) ?? [];
  const moveSection = (from: number, to: number) => void reorder(moveIndex(sectionIds, from, to));
  // --- Phase 6 S4b: a locked course template fixes the sections (add, delete, reorder), design §5.4 ---
  const courseLocked = !!a && isAssessmentLocked(ui, a.preset);
  // --- Phase 7b S5: a locked exam template fixes the sections too (empty set for blank and preset exams) ---
  const examLocks = a ? templateLockedFields(a) : new Set<string>();
  const examStructureLocked = examLocks.has("section_add_remove") || examLocks.has("section_order");
  const structureLocked = courseLocked || examStructureLocked;
  const lockedNote = courseLocked ? t("templates.lockedNote") : t("examTemplates.lockedSections");
  // --- Phase 7b S5 end ---
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
    <Button variant="secondary" disabled={structureLocked} title={structureLocked ? lockedNote : undefined}
      onClick={() => { setSecError(null); setSectionDlg({ section: null }); }}>{t("assessments.section.add")}</Button>
  ) : undefined;
  return (
    <div className="space-y-4">
      {/* Phase 6b S5c: PageHeader with breadcrumbs; the one primary of the page is "Publish" in the publish panel (UX T8). */}
      {/* Phase 6b S11b (UX 3): the assessment name is the title; "Edit" is the last breadcrumb. */}
      <PageHeader breadcrumbs={crumbs} title={title} className="mb-2" />
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
      {canEdit && structureLocked && <p role="note" className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{lockedNote}</p>}
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
