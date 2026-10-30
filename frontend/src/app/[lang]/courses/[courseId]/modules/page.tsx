"use client";

// Phase 8a S4a: `/courses/[courseId]/modules`: the modules view for students (and read-only, without progress, for
// an org admin reading the course).
// Phase 8c S1 (PHASE_8C_DESIGN §4.2 row 3, P8C-3): teachers and assistants edit the outline on the Course page, so
// for them this route is a redirect stub (query and `#m-{id}` fragment carried over); students and org admins keep
// this page.
import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { StudentModulesView } from "@/components/lms/modules/StudentModulesView";
import { LoadingState } from "@/components/ui";
import { isStaffCourse } from "@/lib/lms/types";

export default function ModulesPage() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const role = course.my_enrollment.role;
  const staff = isStaffCourse(course) && (role === "teacher" || role === "assistant") && !course.my_enrollment.read_only;

  useEffect(() => {
    if (!staff) return;
    router.replace(`/${lang}/courses/${course.id}${window.location.search}${window.location.hash}`);
  }, [staff, course.id, lang, router]);

  if (staff) return <LoadingState label={t("lms.common.loading")} />;
  return <StudentModulesView />;
}
