"use client";

// Exam prep S2: the course's exam date on the course settings page (exam-prep courses only). Students see the days
// left on their exam-prep page; an empty date hides the countdown.
import React, { useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { updateCourse } from "@/lib/lms/courses";
import type { CourseStaffOut } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button, Input } from "@/components/ui";

export function ExamDateSection({ course }: { course: CourseStaffOut }) {
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
    <form onSubmit={(ev) => { ev.preventDefault(); void save(value); }} noValidate
      className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
      <h2 className="text-lg font-bold text-slate-900">{t("courses.settings.examDate.title")}</h2>
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
