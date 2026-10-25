"use client";

// Phase 7a S5: the assignment page. Students hand in here; staff are sent to the editor.
import React, { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { StudentAssignmentView } from "@/components/lms/assignments/StudentAssignmentView";
import { LoadingState } from "@/components/ui";

export default function AssignmentPage() {
  const { lang } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const params = useParams<{ assignmentId: string }>();
  const role = course.my_enrollment.role;
  const staff = role === "teacher" || role === "assistant";
  useEffect(() => {
    if (staff) router.replace(`/${lang}/courses/${course.id}/assignments/${params.assignmentId}/edit`);
  }, [staff, router, lang, course.id, params.assignmentId]);
  if (staff) return <LoadingState rows={2} />;
  return <StudentAssignmentView assignmentId={params.assignmentId} />;
}
