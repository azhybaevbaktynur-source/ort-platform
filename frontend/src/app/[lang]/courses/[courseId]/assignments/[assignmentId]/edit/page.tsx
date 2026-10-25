"use client";

// Phase 7a S5: assignment editor (staff). Others see a "no permission" note; the server decides.
import React from "react";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { AssignmentEditor } from "@/components/lms/assignments/AssignmentEditor";
import { EmptyState, LinkButton } from "@/components/ui";

export default function AssignmentEditPage() {
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
  return <AssignmentEditor assignmentId={params.assignmentId} />;
}
