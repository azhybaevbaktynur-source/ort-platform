"use client";

// Exam prep S2: the course's exam date on the course settings page (exam-prep courses only). Students see the days
// left on their exam-prep page; an empty date hides the countdown.
// Step 3a S1 (STUDENT_IA_DESIGN §6.1): the same «Экзамен» section holds the exam group (family) and the subject, for a
// platform admin on a platform course only (the server refuses everyone else: 422 `exam_family_forbidden`).
import React, { useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { updateCourse } from "@/lib/lms/courses";
import { EXAM_FAMILIES, EXAM_SUBJECTS, type CourseStaffOut, type ExamFamily, type ExamSubject } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button, Input, Select } from "@/components/ui";

function ExamDateForm({ course }: { course: CourseStaffOut }) {
  const { t } = useTranslation();
  const { setCourse } = useCourse();
  const saved0 = course.exam_date ?? "";
  const [value, setValue] = useState(saved0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  const save = async (next: string) => {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const c = await updateCourse(course.id, { exam_date: next || null });
      setCourse(c);
      setValue(c.exam_date ?? "");
      setSaved(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(ev) => { ev.preventDefault(); void save(value); }} noValidate className="space-y-4">
      <Input type="date" label={t("courses.settings.examDate.label")} hint={t("courses.settings.examDate.hint")}
        containerClassName="max-w-xs" value={value} min="2020-01-01" max="2100-12-31" disabled={busy}
        onChange={(e) => { setValue(e.target.value); setSaved(false); }} />
      <ErrorMessage error={error} />
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="sm" loading={busy} disabled={value === saved0}>{t("lms.common.save")}</Button>
        {saved0 && (
          <Button variant="link" onClick={() => void save("")} disabled={busy}>{t("courses.settings.examDate.clear")}</Button>
        )}
        {saved && <p role="status" className="text-sm text-success-700">{t("courses.settings.saved")}</p>}
      </div>
    </form>
  );
}

function ExamFamilyForm({ course }: { course: CourseStaffOut }) {
  const { t } = useTranslation();
  const { setCourse } = useCourse();
  const savedFamily = course.exam_family ?? "";
  const savedSubject = course.subject ?? "";
  const [family, setFamily] = useState<ExamFamily | "">(savedFamily);
  const [subject, setSubject] = useState<ExamSubject | "">(savedSubject);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  // a subject belongs to a family: no family, no subject
  const nextSubject = family ? subject : "";
  const changed = family !== savedFamily || nextSubject !== savedSubject;

  const save = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const c = await updateCourse(course.id, { exam_family: family || null, subject: nextSubject || null });
      setCourse(c);
      setFamily(c.exam_family ?? "");
      setSubject(c.subject ?? "");
      setSaved(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(ev) => { ev.preventDefault(); void save(); }} noValidate className="space-y-4"
      data-testid="settings-exam-family">
      <div className="flex flex-col gap-4 sm:flex-row">
        <Select id="s-exam-family" containerClassName="min-w-0 sm:w-64" label={t("courses.settings.examDate.familyLabel")}
          value={family} disabled={busy} aria-describedby="s-exam-family-help"
          onChange={(e) => { setFamily(e.target.value as ExamFamily | ""); setSaved(false); }}
          options={[
            { value: "", label: t("courses.settings.examDate.familyNone") },
            ...EXAM_FAMILIES.map((f) => ({ value: f, label: t(`exam.family.${f}`) })),
          ]} />
        <Select id="s-exam-subject" containerClassName="min-w-0 sm:w-64" label={t("courses.settings.examDate.subjectLabel")}
          value={nextSubject} disabled={busy || !family}
          onChange={(e) => { setSubject(e.target.value as ExamSubject | ""); setSaved(false); }}
          options={[
            { value: "", label: t("courses.settings.examDate.subjectMain") },
            ...EXAM_SUBJECTS.map((s) => ({ value: s, label: t(`exam.subject.${s}`) })),
          ]} />
      </div>
      <p id="s-exam-family-help" className="text-sm leading-5 text-slate-600">{t("courses.settings.examDate.familyHelp")}</p>
      <ErrorMessage error={error} />
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="sm" loading={busy} disabled={!changed}>{t("lms.common.save")}</Button>
        {saved && <p role="status" className="text-sm text-success-700">{t("courses.settings.saved")}</p>}
      </div>
    </form>
  );
}

/** The «Экзамен» section: the exam date (`showDate`: exam-prep courses) and the exam group and subject (`showFamily`:
 * a platform admin on a platform course), each with its own Save. */
export function ExamDateSection({ course, showDate = true, showFamily = false }: {
  course: CourseStaffOut; showDate?: boolean; showFamily?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
      <h2 className="text-lg font-bold text-slate-900">{t("courses.settings.examDate.title")}</h2>
      {showDate && <ExamDateForm course={course} />}
      {showDate && showFamily && <hr className="border-slate-100" />}
      {showFamily && <ExamFamilyForm course={course} />}
    </section>
  );
}
