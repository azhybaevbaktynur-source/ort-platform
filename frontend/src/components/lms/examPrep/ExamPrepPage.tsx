"use client";

// Exam prep S2 (docs/ROADMAP_EXAM_PREP.md S2): the students' page of an exam-prep course (the course template chooses
// it; ORT first). One read for the page, one paginated read for the library. Top to bottom on a wide screen: goal
// strip, the one "Next" card, score history and section bars, the test library (UX review: Next right after the goals). Phones put the cards first: goal strip,
// Next, the library, then the history and the bars. Numbers are big and plain; unreleased results carry no number.
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { getExamPrep, type ExamPrepOut } from "@/lib/lms/examPrep";
import { useCourse } from "@/components/lms/CourseContext";
import { ErrorState, Skeleton } from "@/components/ui";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { LeaveCourseLink } from "@/components/lms/home/LeaveCourseLink";
import { GoalStrip } from "./GoalStrip";
import { NextCard } from "./NextCard";
import { ScoreHistory } from "./ScoreHistory";
import { SectionBars } from "./SectionBars";
import { TestLibrary } from "./TestLibrary";

function PageSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-live="polite" className="space-y-6">
      <span className="sr-only">{t("ui.loading")}</span>
      <div aria-hidden="true" className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-28 w-full rounded-2xl" />)}
      </div>
      <Skeleton aria-hidden="true" className="h-36 w-full rounded-2xl" />
      <div aria-hidden="true" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-40 w-full rounded-2xl" />)}
      </div>
    </div>
  );
}

export function ExamPrepPage() {
  const { course } = useCourse();
  const errorText = useErrorText();
  const [data, setData] = useState<ExamPrepOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getExamPrep(course.id));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id]);
  useEffect(() => { void load(); }, [load]);

  if (error && !data) return <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />;
  if (!data) return <PageSkeleton />;

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:items-start">
        <GoalStrip data={data} courseId={course.id} onGoal={(goal) => setData({ ...data, goal })} className="lg:col-span-2" />
        <NextCard next={data.next} courseId={course.id} className="order-2 lg:order-none lg:col-span-2" />
        <ScoreHistory data={data} className="order-4 lg:order-none" />
        <SectionBars data={data} className="order-5 lg:order-none" />
        <TestLibrary courseId={course.id} sources={data.sources} total={data.library_total} className="order-3 lg:order-none lg:col-span-2" />
      </div>
      <LeaveCourseLink />
    </div>
  );
}
