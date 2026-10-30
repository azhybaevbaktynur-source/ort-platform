"use client";

// Phase 9 S4: Settings → Enrollment → Enrollment form (PHASE_9_DESIGN 8.1): one page per object, Edit · Preview tabs.
// Teachers edit; assistants read (the server decides: builder writes are teacher-only).
import React, { Suspense } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { isStaffCourse } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { FormBuilder } from "@/components/lms/enrollmentForm/FormBuilder";
import { LoadingState } from "@/components/ui";

export default function EnrollmentFormPage() {
  const { course } = useCourse();
  const { t } = useTranslation();
  if (!isStaffCourse(course) || (course.my_enrollment.role !== "teacher" && course.my_enrollment.role !== "assistant")) {
    return <p className="text-sm text-slate-600">{t("lms.errors.forbidden")}</p>;
  }
  return <Suspense fallback={<LoadingState />}><FormBuilder key={course.id} course={course} /></Suspense>;
}
