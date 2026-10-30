"use client";

// Phase 7a S5: assignment editor (PHASE_7A_DESIGN 5): the fields of section 2.1, saved through the assignment PATCH.
// For a quiz the assessment stays the source of truth (section 3.2): the same fields are saved through the assignment
// (the server delegates them to the builder; 409 template_locked shows the locked note) and "Open exam builder" leads
// to the questions and the exam settings. Rubric and exceptions sit below. Phase 8c S3: the Settings tab of the
// assignment page (`AssignmentPage`), no header of its own.
import React, { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { updateAssignment } from "@/lib/lms/assignments";
import type { AssignmentStaffOut, AssignmentUpdateIn } from "@/lib/lms/assignmentTypes";
import { GRADE_RELEASES, type GradeRelease } from "@/lib/lms/gradingTypes";
import { cleanLocalized, pickLocalized } from "@/lib/lms/localized";
import { isAssessmentLocked, useTemplateUi } from "@/lib/lms/templates";
import type { LocalizedText } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { SchemePicker } from "@/components/lms/grading/settings/SchemePicker";
import { fromLocalInput, toLocalInput } from "@/components/lms/assessments/format";
import {
  Button, Card, Checkbox, FieldLabel, Input, Select, toast,
} from "@/components/ui";
import { OverridesPanel } from "@/components/lms/accommodations/OverridesPanel";
import { AssignmentError, fmtPts, parsePoints } from "./assignmentUi";
import { RubricEditor } from "./RubricEditor";
import { useCategories } from "./useCategories";

interface Form {
  title: LocalizedText;
  description: LocalizedText;
  points: string;
  due: string;
  from: string;
  until: string;
  category: string;
  scheme: string | null;
  release: GradeRelease;
  omit: boolean;
}

const formOf = (a: AssignmentStaffOut): Form => ({
  title: a.title ?? {},
  description: a.description ?? {},
  points: fmtPts(a.points_possible),
  due: toLocalInput(a.due_at),
  from: toLocalInput(a.available_from),
  until: toLocalInput(a.available_until),
  category: a.category_id ?? "",
  scheme: a.grading_scheme_version_id,
  release: a.grade_release,
  omit: a.omit_from_total,
});

export interface AssignmentEditorHandle {
  /** The form has changes that are not saved yet. */
  isDirty: () => boolean;
  /** Saves the form; false when it is invalid or the server refused it (the form shows why). */
  save: () => Promise<boolean>;
}

/**
 * Phase 8c S3 (PHASE_8C_DESIGN §5.1): the Settings tab of the assignment page. The page loads the assignment, owns the
 * header (title, badges, Publish) and passes the assignment in; "Grade" and "Open exam builder" moved to the header
 * and the Details tab. The page asks `isDirty`/`save` through the ref before publishing (unsaved changes first).
 */
export const AssignmentEditor = forwardRef<AssignmentEditorHandle, {
  assignment: AssignmentStaffOut;
  onChange: (a: AssignmentStaffOut) => void;
}>(function AssignmentEditor({ assignment: a, onChange }, ref) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const isTeacher = course.my_enrollment.role === "teacher";
  const ui = useTemplateUi();
  const categories = useCategories(course.id);
  const [form, setForm] = useState<Form>(() => formOf(a));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [locked, setLocked] = useState(false);
  const [touched, setTouched] = useState(false);

  const quiz = a.kind === "quiz";
  const preset = a.assessment?.preset ?? null;
  const ortLocked = quiz && isAssessmentLocked(ui, preset);
  const set = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }));
  const pts = parsePoints(form.points);
  const pointsOk = quiz || (pts !== null && !Number.isNaN(pts) && pts >= 0 && pts <= 10000);
  const fromIso = fromLocalInput(form.from);
  const untilIso = fromLocalInput(form.until);
  const windowBad = !!fromIso && !!untilIso && Date.parse(fromIso) >= Date.parse(untilIso);
  const titleOk = Object.keys(cleanLocalized(form.title, course.languages)).length > 0;
  const disabled = !canEdit || !!a.deleted_at;

  // Phase 7a UX: form values as saved (localized texts cleaned, so an emptied extra language is not a change)
  const norm = (f: Form) => JSON.stringify({ ...f, title: cleanLocalized(f.title, course.languages), description: cleanLocalized(f.description, course.languages) });
  const formDirty = norm(form) !== norm(formOf(a));

  const saveForm = async (): Promise<boolean> => {
    setTouched(true);
    if (!pointsOk || windowBad || !titleOk) return false;
    setBusy(true);
    setError(null);
    setLocked(false);
    const body: AssignmentUpdateIn = {
      title: cleanLocalized(form.title, course.languages),
      description: cleanLocalized(form.description, course.languages),
      due_at: fromLocalInput(form.due),
      available_from: fromIso,
      available_until: untilIso,
      category_id: form.category || null,
      grade_release: form.release,
      omit_from_total: form.omit,
      ...(ortLocked ? {} : { grading_scheme_version_id: form.scheme }),
      ...(quiz ? {} : { points_possible: pts }),
    };
    try {
      const out = await updateAssignment(course.id, a.id, body);
      onChange(out);
      setForm(formOf(out));
      toast.success(t("assignments.editor.saved"));
      return true;
    } catch (err) {
      if ((err as { code?: string }).code === "template_locked") setLocked(true);
      setError(err);
      return false;
    } finally {
      setBusy(false);
    }
  };
  const live = useRef({ formDirty, saveForm });
  live.current = { formDirty, saveForm };
  useImperativeHandle(ref, () => ({ isDirty: () => live.current.formDirty, save: () => live.current.saveForm() }), []);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    await saveForm();
  };

  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-600">{quiz ? t("assignments.editor.quizHint") : t("assignments.editor.publishedHint")}</p>
      {a.deleted_at && <p role="status" className="rounded-xl border border-slate-200 bg-slate-100 px-3 py-2 text-sm text-slate-700">{t("assignments.editor.deletedNote")}</p>}

      <form onSubmit={(e) => void save(e)} className="space-y-6">
        <Card title={t("assignments.editor.basics")}>
          <div className="space-y-4">
            <LocalizedTextInput label={t("assignments.create.titleLabel")} languages={course.languages} defaultLanguage={course.default_language}
              value={form.title} onChange={(v) => set({ title: v })} maxLength={200} required disabled={disabled} />
            {touched && !titleOk && <p className="text-sm text-danger-700">{t("assignments.create.titleRequired")}</p>}
            <div>
              <LocalizedTextInput label={t("assignments.fields.instructions")} languages={course.languages} defaultLanguage={course.default_language}
                value={form.description} onChange={(v) => set({ description: v })} multiline disabled={disabled} />
              <p className="mt-1 text-sm text-slate-600">{t("assignments.fields.instructionsHint")}</p>
            </div>
            {!quiz && (
              <Input label={t("assignments.fields.points")} inputMode="decimal" value={form.points} disabled={disabled}
                onChange={(e) => set({ points: e.target.value })} hint={t("assignments.fields.pointsHint")}
                error={touched && !pointsOk ? t("assignments.fields.pointsInvalid") : undefined} containerClassName="sm:max-w-xs" />
            )}
            {quiz && <p className="text-sm text-slate-600">{a.published ? t("assignments.editor.quizPublished") : t("assignments.editor.quizDraft")}</p>}
          </div>
        </Card>

        <Card title={t("assignments.editor.dates")} description={t("assignments.editor.datesHint")}>
          <div className="grid gap-4 sm:grid-cols-3">
            <Input type="datetime-local" label={t("assignments.fields.due")} optional value={form.due} disabled={disabled} onChange={(e) => set({ due: e.target.value })} />
            <Input type="datetime-local" label={t("assignments.fields.availableFrom")} optional value={form.from} disabled={disabled} onChange={(e) => set({ from: e.target.value })} />
            <Input type="datetime-local" label={t("assignments.fields.availableUntil")} optional value={form.until} disabled={disabled}
              onChange={(e) => set({ until: e.target.value })} error={windowBad ? t("assignments.fields.windowInvalid") : undefined} />
          </div>
        </Card>

        <Card title={t("assignments.editor.grading")}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <FieldLabel htmlFor="asg-scheme">{t("grading.settings.scheme")}</FieldLabel>
              <div className="mt-1">
                <SchemePicker id="asg-scheme" value={form.scheme} current={null} disabled={disabled || ortLocked}
                  defaultLanguage={course.default_language} onChange={(id) => set({ scheme: id })} />
              </div>
              <p className="mt-1 text-sm text-slate-600">{ortLocked ? t("templates.lockedNote") : t("grading.settings.schemeHint")}</p>
            </div>
            <Select label={t("grading.settings.category")} value={form.category} disabled={disabled} onChange={(e) => set({ category: e.target.value })}
              options={[{ value: "", label: t("grading.settings.noCategory") }, ...categories.map((c) => ({ value: c.id, label: pickLocalized(c.title, lang, course.default_language) || "—" }))]} />
            <Select label={t("grading.settings.release")} value={form.release} disabled={disabled} onChange={(e) => set({ release: e.target.value as GradeRelease })}
              hint={t(`grading.settings.releaseHint.${form.release}`)}
              options={GRADE_RELEASES.map((r) => ({ value: r, label: t(`grading.settings.releaseModes.${r}`) }))} />
            <div className="sm:pt-6">
              <Checkbox label={t("grading.settings.omit")} checked={form.omit} disabled={disabled} onChange={(e) => set({ omit: e.target.checked })} />
            </div>
          </div>
        </Card>

        {locked && <p role="status" className="rounded-xl border border-slate-200 bg-slate-100 px-3 py-2 text-sm text-slate-700">{t("templates.lockedNote")}</p>}
        <AssignmentError error={error} />
        {canEdit && !a.deleted_at && (
          <div className="flex flex-col gap-2 sm:flex-row [&>*]:w-full sm:[&>*]:w-auto">
            <Button type="submit" loading={busy}>{t("assignments.editor.save")}</Button>
          </div>
        )}
      </form>

      {!quiz && (
        <RubricEditor courseId={course.id} assignment={a} defaultLanguage={course.default_language} canEdit={canEdit && !a.deleted_at}
          onSaved={(rubric) => onChange({ ...a, rubric })} />
      )}

      {isTeacher && !a.deleted_at && (
        <OverridesPanel courseId={course.id} assignmentId={a.id} isQuiz={quiz} ortTimeLocked={!!preset && preset !== "none"} canEdit={canEdit} />
      )}
    </div>
  );
});
