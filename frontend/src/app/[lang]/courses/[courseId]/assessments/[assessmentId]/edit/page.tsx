"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { getAssessment } from "@/lib/lms/assessments";
import { isStaffAssessment, type AssessmentStaffOut } from "@/lib/lms/assessmentTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { StaffGate } from "@/components/lms/content/StaffGate";
import { LoadingState } from "@/components/ui";
import { AssessmentError } from "@/components/lms/assessments/AssessmentError";
import { SectionBuilder } from "@/components/lms/assessments/SectionBuilder";
import { QuizEditor } from "@/components/lms/quiz/QuizEditor";

export default function AssessmentEditPage() {
  return <StaffGate><EditorSwitch /></StaffGate>;
}

/**
 * Phase 7c S3 (PHASE_7C_DESIGN 8.1, 7c-8): preset exams (ORT) keep the section builder pixel for pixel; blank and
 * template-created quizzes get the question-card editor. The assessment is loaded once here and handed down.
 */
function EditorSwitch() {
  const { lang } = useTranslation();
  const { course } = useCourse();
  const params = useParams<{ assessmentId: string }>();
  const router = useRouter();
  const aid = params.assessmentId;
  const [a, setA] = useState<AssessmentStaffOut | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    try {
      const out = await getAssessment(course.id, aid);
      if (!isStaffAssessment(out)) { router.replace(`/${lang}/courses/${course.id}/assessments/${aid}`); return; }
      setA(out);
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [course.id, aid, lang, router]);
  useEffect(() => { void load(); }, [load]);

  if (error && !a) return <AssessmentError error={error} onRetry={() => void load()} />;
  if (!a) return <LoadingState rows={3} />;
  return a.preset !== "none" ? <SectionBuilder initial={a} /> : <QuizEditor initial={a} />;
}
