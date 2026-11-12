"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCourse } from "@/components/lms/CourseContext";
import { AnalyticsOverview, PeriodPicker } from "@/components/lms/progress/AnalyticsOverview";
import { LoadingState } from "@/components/ui";
import { StudentPageHeader } from "@/components/lms/student/StudentPageHeader";
import { ToCourseTab } from "@/components/lms/course/ToCourseTab"; // step 3a S2
import { useTranslation } from "@/lib/i18n/context";
import { inCourseSpace, templateUi } from "@/lib/lms/templates";
import type { ActivityDays } from "@/lib/lms/progress";

function Analytics() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const examPrep = templateUi(course).studentLayout === "exam_prep";
  const params = useSearchParams();
  // Student UI U8 (§5.1 a): the mistakes notebook moved to Сохранённые; old links still land there
  const mistakes = params.get("tab") === "mistakes";
  useEffect(() => {
    if (mistakes) router.replace(`/${lang}/courses/${course.id}/saved?tab=mistakes`);
  }, [mistakes, lang, course.id, router]);
  const [period, setPeriod] = useState<ActivityDays>(30);
  if (mistakes) return <LoadingState label={t("lms.common.loading")} />;
  // step 3a S2 (STUDENT_IA_DESIGN §3.7, N4): a student's analytics is the course's Аналитика tab
  if (inCourseSpace(course)) return <ToCourseTab courseId={course.id} path="/analytics" />;
  return (
    <div className="space-y-4">
      <StudentPageHeader title={t("progress.analytics.title")} className="mb-2"
        action={<PeriodPicker value={period} onChange={setPeriod} />} />
      <AnalyticsOverview courseId={course.id} period={period} examPrep={examPrep} />
    </div>
  );
}

/** `/progress`: students go to the Аналитика tab, `?tab=mistakes` to Сохранённые (U8). The server answers 404 for staff. */
export default function ProgressPage() {
  return (
    <Suspense fallback={null}>
      <Analytics />
    </Suspense>
  );
}
