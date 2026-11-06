"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { leaveCourse } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import { isStaffCourse } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { TeacherCoursePage } from "@/components/lms/course/TeacherCoursePage"; // Phase 8c S2
import { StudentCourseHome } from "@/components/lms/home/StudentCourseHome"; // Phase 6 S6b
import { StudentModulesView } from "@/components/lms/modules/StudentModulesView"; // Phase 8a S4a
import { PageView } from "@/components/lms/pages/PageView"; // Phase 8a S4a (home_kind = page)
import { CourseLoadingSkeleton } from "@/components/lms/home/StudentCourseFrame";
import { templateUi } from "@/lib/lms/templates";

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

  // --- Phase 8c S2 begin --- (PHASE_8C_DESIGN §3: the teacher Course page: modules outline, Unsorted, To do; ORT
  // courses: the exam list with To do and the outline collapsed below. Replaces the 6b staff course home.)
  if (isStaffCourse(course) && (course.my_enrollment.role === "teacher" || course.my_enrollment.role === "assistant")
    && !course.my_enrollment.read_only) {
    return <TeacherCoursePage course={course} />;
  }
  // --- Phase 8c S2 end ---
  // --- Phase 6 S6b begin --- (student view: next assessment, latest result, about; UX S5)
  // --- UX rework B (PUR-4): `page` shows the chosen page, then the modules below it; otherwise published modules are
  // the home whatever `home_kind` says, ORT included (its exam rows open the same lobby); without them, today's home.
  if (course.my_enrollment.role === "student") {
    // Exam prep S2 (owner 2026-11-06): the course template chooses the exam-prep layout (ORT first); Student view too.
    // Student UI U4 (STUDENT_UI_DESIGN §3.2): its students land on the Тесты page; the home is the dashboard (U3).
    if (templateUi(course).studentLayout === "exam_prep") return <ToTests courseId={course.id} />;
    if (course.home_kind === "page" && course.home_page_id) {
      return (
        <div className="space-y-6">
          <PageView pageId={course.home_page_id} embedded />
          {course.features?.modules && <StudentModulesView fallback={null} />}
        </div>
      );
    }
    if (course.features?.modules) return <StudentModulesView fallback={<StudentCourseHome />} />;
    return <StudentCourseHome />;
  }
  // --- Phase 8a S4a end ---
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

/** Student UI U4: `/courses/{c}` of an exam-prep course is `/courses/{c}/tests` for its students (client-side, replace). */
function ToTests({ courseId }: { courseId: string }) {
  const { lang } = useTranslation();
  const router = useRouter();
  useEffect(() => {
    router.replace(`/${lang}/courses/${courseId}/tests${window.location.search}`);
  }, [router, lang, courseId]);
  return <CourseLoadingSkeleton />;
}
