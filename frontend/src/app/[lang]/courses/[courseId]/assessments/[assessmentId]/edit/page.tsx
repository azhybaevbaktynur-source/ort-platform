"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { addSection, deleteSection, getAssessment, reorderSections, updateSection } from "@/lib/lms/assessments";
import { isStaffAssessment, type AssessmentStaffOut, type SectionIn, type SectionOut } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { isAssessmentLocked, useTemplateUi } from "@/lib/lms/templates";
import { useCourse } from "@/components/lms/CourseContext";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { StaffGate, useCanEditContent } from "@/components/lms/content/StaffGate";
import { btnPrimary } from "@/components/lms/content/ui";
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

  if (error && !a) return <AssessmentError error={error} onRetry={() => void load()} />;
  if (!a) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;

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

  const title = pickLocalized(a.title, lang, course.default_language) || t("assessments.untitled");
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link href={`${base}/${a.id}`} className="text-sm font-medium text-brand-700 hover:underline">{t("assessments.builder.back")}</Link>
        <h2 className="text-lg font-bold text-slate-900">{t("assessments.builder.title", { title })}</h2>
      </div>
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
        <h3 className="text-base font-bold text-slate-900">{t("assessments.builder.sections")}</h3>
        {canEdit && <button type="button" className={btnPrimary} disabled={structureLocked} onClick={() => { setSecError(null); setSectionDlg({ section: null }); }}>{t("assessments.section.add")}</button>}
      </div>
      {canEdit && structureLocked && <p role="note" className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">{t("templates.lockedNote")}</p>}
      <AssessmentError error={actionError} />
      {a.sections.length === 0 && <p className="text-sm text-slate-500">{t("assessments.builder.noSections")}</p>}
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
      <ConfirmDialog open={!!toDelete} danger busy={secBusy} title={t("assessments.section.deleteTitle")}
        body={t("assessments.section.deleteBody", { name: toDelete ? sectionName(toDelete, lang, course.default_language, t) : "" })}
        confirmLabel={t("assessments.section.delete")} onConfirm={() => void removeSection()} onCancel={() => setToDelete(null)}>
        <AssessmentError error={secError} className="mt-3" />
      </ConfirmDialog>
      {addTo && (
        <AddItemsDialog open courseId={course.id} assessmentId={a.id} sectionId={addTo} onClose={() => setAddTo(null)} onAdded={load} />
      )}
    </div>
  );
}
