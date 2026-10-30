"use client";

// Phase 8c S1 (PHASE_8C_DESIGN §4.2 rows 1-2, P8C-3, P8C-7): the Tests list is gone. This route stays one phase as a
// redirect stub (removed at the Phase 9 kickoff): quizzes live in Assignments (`?kind=quiz`); "New" (`?new=1`) opens
// the quiz form in Assignments (general courses) or the exam list on the ORT Course page. Other query parameters are
// carried over. `/assessments/{id}*` (lobby, builder, results) are unchanged.
import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { templateUi } from "@/lib/lms/templates";
import { useCourse } from "@/components/lms/CourseContext";
import { LoadingState } from "@/components/ui";

export default function AssessmentsRedirect() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();

  useEffect(() => {
    const base = `/${lang}/courses/${course.id}`;
    const params = new URLSearchParams(window.location.search);
    const role = course.my_enrollment.role;
    const staff = (role === "teacher" || role === "assistant") && !course.my_enrollment.read_only;
    const ui = templateUi(course);
    let target = `${base}/assignments`;
    if (staff && params.get("new") === "1") {
      params.delete("new");
      if (ui.locked && ui.key === "ort") {
        params.set("new", "1"); // the ORT exam list on the Course page opens its create dialog
        target = base;
      } else {
        params.set("new", "quiz");
      }
    } else {
      params.delete("new");
      params.set("kind", "quiz");
    }
    const qs = params.toString();
    router.replace(`${target}${qs ? `?${qs}` : ""}${window.location.hash}`);
  }, [course, lang, router]);

  return <LoadingState label={t("lms.common.loading")} />;
}
