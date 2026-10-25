"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { leaveCourse } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import { isStaffCourse } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { StaffCourseHome } from "@/components/lms/course/StaffCourseHome"; // Phase 6b S5c
import { StudentCourseHome } from "@/components/lms/home/StudentCourseHome"; // Phase 6 S6b

export default function CourseHomePage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { course } = useCourse();
  const [leaving, setLeaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const description = pickLocalized(course.description, lang, course.default_language);
  const isOwner = isStaffCourse(course) && course.is_owner;

  const leave = async () => {
    setBusy(true);
    setError(null);
    try {
      await leaveCourse(course.id);
      router.push(`/${lang}/courses`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  // --- Phase 6b S5c: staff course home (next step instead of the roadmap sentence) ---
  if (isStaffCourse(course) && (course.my_enrollment.role === "teacher" || course.my_enrollment.role === "assistant")) {
    return <StaffCourseHome course={course} />;
  }
  // --- Phase 6b S5c end ---
  // --- Phase 6 S6b begin --- (student view: next assessment, latest result, about; UX S5)
  if (course.my_enrollment.role === "student") return <StudentCourseHome />;
  // --- Phase 6 S6b end ---

  return (
    <div className="space-y-6">
      {course.status === "draft" && (
        <p role="status" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">{t("courses.home.draftNotice")}</p>
      )}
      {course.status === "concluded" && (
        <p role="status" className="rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-sm text-slate-700">{t("courses.home.concludedNotice")}</p>
      )}
      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">{t("courses.home.about")}</h2>
        <p className="whitespace-pre-line text-sm text-slate-800">{description || t("courses.home.noDescription")}</p>
        <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-slate-500">{t("courses.home.owner")}</dt>
            <dd className="font-medium text-slate-900">{course.owner_display_name || "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">{t("courses.home.myRole")}</dt>
            <dd className="font-medium text-slate-900">{t(`courses.roles.${course.my_enrollment.role}`)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">{t("courses.home.languages")}</dt>
            <dd className="font-medium text-slate-900">{course.languages.map((l) => t(`courses.languages.${l}`)).join(", ")}</dd>
          </div>
          {isStaffCourse(course) && (
            <div>
              <dt className="text-slate-500">{t("courses.home.activeStudents")}</dt>
              <dd className="font-medium text-slate-900">
                {course.active_student_count}
                {course.enrollment_limit ? ` / ${course.enrollment_limit}` : ""}
              </dd>
            </div>
          )}
        </dl>
      </section>
      <p className="text-sm text-slate-500">{t("courses.home.contentSoon")}</p>
      {!isOwner && (
        <div>
          <button type="button" onClick={() => setLeaving(true)} className="text-sm font-semibold text-red-600 hover:underline">{t("courses.home.leave")}</button>
        </div>
      )}
      <ConfirmDialog open={leaving} danger busy={busy} error={error} title={t("courses.home.leaveTitle")} body={t("courses.home.leaveBody")}
        confirmLabel={t("courses.home.leave")} onConfirm={leave} onCancel={() => setLeaving(false)} />
    </div>
  );
}
