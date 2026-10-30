"use client";

// Phase 8c S3 (PHASE_8C_DESIGN §4.2): redirect stub, kept one phase (removed at the Phase 9 kickoff). Staff go to the
// assignment page's Settings tab (query carried over); others see the "no permission" note as before (the student
// view sends a staff-shaped answer here, so sending them back to the assignment would loop).
import React from "react";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { RedirectStub } from "@/components/lms/assignments/objectNav";
import { EmptyState, LinkButton } from "@/components/ui";

export default function AssignmentEditRedirect() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const params = useParams<{ assignmentId: string }>();
  const role = course.my_enrollment.role;
  const base = `/${lang}/courses/${course.id}`;
  if (role !== "teacher" && role !== "assistant") {
    return (
      <EmptyState title={t("assignments.noPermission")} description={t("assignments.noPermissionHint")}
        action={<LinkButton variant="secondary" href={`${base}/assignments`}>{t("assignments.backToList")}</LinkButton>} />
    );
  }
  return <RedirectStub target={`${base}/assignments/${params.assignmentId}`} set={{ tab: "settings" }} />;
}
