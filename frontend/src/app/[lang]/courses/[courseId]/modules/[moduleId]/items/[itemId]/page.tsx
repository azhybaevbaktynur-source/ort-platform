"use client";

// Student UI U7 (docs/phases/STUDENT_UI_DESIGN.md §3.5): the lesson page of a module item (video player, link or file
// card, mark as done, previous / next). Teachers and assistants edit on the Course page: this route sends them there.
import React, { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { LessonView } from "@/components/lms/modules/LessonView";
import { LoadingState } from "@/components/ui";
import { isStaffCourse } from "@/lib/lms/types";

export default function LessonPage() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const { moduleId, itemId } = useParams<{ moduleId: string; itemId: string }>();
  const role = course.my_enrollment.role;
  const staff = isStaffCourse(course) && (role === "teacher" || role === "assistant") && !course.my_enrollment.read_only;

  useEffect(() => {
    if (staff) router.replace(`/${lang}/courses/${course.id}`);
  }, [staff, course.id, lang, router]);

  if (staff) return <LoadingState label={t("lms.common.loading")} />;
  return <LessonView key={`${moduleId}/${itemId}`} moduleId={moduleId} itemId={itemId} />;
}
