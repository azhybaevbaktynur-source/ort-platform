"use client";

// Phase 7a S5: grading screen (staff).
import React from "react";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { GradingScreen } from "@/components/lms/assignments/GradingScreen";
import { EmptyState, LinkButton } from "@/components/ui";

export default function AssignmentGradePage() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const params = useParams<{ assignmentId: string }>();
  const role = course.my_enrollment.role;
  if (role !== "teacher" && role !== "assistant") {
    return (
      <EmptyState title={t("assignments.noPermission")} description={t("assignments.noPermissionHint")}
        action={<LinkButton variant="secondary" href={`/${lang}/courses/${course.id}/assignments`}>{t("assignments.backToList")}</LinkButton>} />
    );
  }
  return <GradingScreen assignmentId={params.assignmentId} />;
}
