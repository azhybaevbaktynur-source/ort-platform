"use client";

// Step 3a S2 (docs/phases/STUDENT_IA_DESIGN.md §3.2, D3, N4): the Аналитика tab of a course for its students,
// `/courses/{c}/analytics` (staff keep the quiz statistics page at the same URL). Block «Оценки» (`#grades`: released
// grades, feedback, the course total; today's `StudentGrades`) when the course has hand-ins or is not an exam course,
// then today's analytics (sections, weak topics, activity, heatmap, streak, score history) when it has tests or lesson
// quizzes (lesson course requests C3; an empty «Оценки» is then hidden). The
// server decides what each read returns (nothing before a release).
import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { ActivityDays } from "@/lib/lms/progress";
import { templateUi } from "@/lib/lms/templates";
import { useCourse } from "@/components/lms/CourseContext";
import { StudentGrades } from "@/components/lms/results/StudentGrades";
import { StudentPageHeader } from "@/components/lms/student/StudentPageHeader";
import { AnalyticsOverview, PeriodPicker } from "./AnalyticsOverview";

export function StudentAnalyticsTab() {
  const { t } = useTranslation();
  const { course } = useCourse();
  const exam = templateUi(course).studentLayout === "exam_prep";
  const f = course.features;
  // lesson course requests C3 (R3, R4): lesson quizzes give the analytics blocks too; «Оценки» (lesson quizzes are no
  // grades) is hidden while the student has no grade rows and the analytics blocks are there to show
  const showAnalytics = !f || !!f.tests || !!f.lesson_quizzes;
  const [gradeRows, setGradeRows] = useState<number | null>(null);
  const gradesBlock = !f || !!f.hand_ins || !exam;
  const showGrades = gradesBlock && !(showAnalytics && gradeRows === 0);
  const [period, setPeriod] = useState<ActivityDays>(30);
  // `#grades` (old `/grades` links): scroll there once the block exists
  useEffect(() => {
    if (window.location.hash !== "#grades") return;
    const id = window.setTimeout(() => document.getElementById("grades")?.scrollIntoView(), 300);
    return () => window.clearTimeout(id);
  }, []);
  return (
    <div className="space-y-6">
      <StudentPageHeader title={t("progress.analytics.title")} className="mb-2"
        action={showAnalytics ? <PeriodPicker value={period} onChange={setPeriod} /> : undefined} />
      {gradesBlock && (
        <section id="grades" aria-label={t("course.analytics.gradesSection")} className="scroll-mt-24" hidden={!showGrades}>
          <StudentGrades courseId={course.id} onRows={setGradeRows} />
        </section>
      )}
      {showAnalytics && <AnalyticsOverview courseId={course.id} period={period} examPrep={exam} />}
    </div>
  );
}
