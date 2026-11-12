"use client";

// Phase 8a S4a: `/courses/[courseId]/modules`: the modules view for students (and read-only, without progress, for
// an org admin reading the course).
// Phase 8c S1 (PHASE_8C_DESIGN §4.2 row 3, P8C-3): teachers and assistants edit the outline on the Course page, so
// for them this route is a redirect stub (query and `#m-{id}` fragment carried over); students and org admins keep
// this page.
// Student UI U7 (STUDENT_UI_DESIGN §3.5): students get the syllabus (start card, progress, collapsible modules, About);
// org admins reading the course keep the modules list without progress.
import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { StudentModulesView } from "@/components/lms/modules/StudentModulesView";
import { StudentSyllabus } from "@/components/lms/modules/StudentSyllabus";
import { LoadingState } from "@/components/ui";
import { isStaffCourse } from "@/lib/lms/types";
import { ToCourseTab } from "@/components/lms/course/ToCourseTab"; // step 3a S2
import { inCourseSpace } from "@/lib/lms/templates"; // step 3a S2

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
  // step 3a S2 (§3.7): the syllabus is the Уроки tab (`#m-{id}` / `#module-{id}` kept)
  if (inCourseSpace(course)) return <ToCourseTab courseId={course.id} path="/lessons" />;
  return role === "student" ? <StudentSyllabus /> : <StudentModulesView />;
}
