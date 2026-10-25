"use client";

// Phase 6b S6b (UX S1, S6, S16): status badge, due date, duration and attempts left per row; one primary button
// for the row that is in progress or next; after the last attempt the row links to the result.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ClipboardList } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listAssessments } from "@/lib/lms/assessments";
import type { AssessmentStudentSummaryOut } from "@/lib/lms/assessmentTypes";
import { getMyGrades } from "@/lib/lms/grading";
import type { MyGradeOut } from "@/lib/lms/gradingTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { useCourse } from "@/components/lms/CourseContext";
import { EmptyState, ErrorState, LoadingState, Pagination } from "@/components/ui";
import { primaryAssessmentId, studentAssessmentView } from "@/components/lms/home/assessmentStatus";
import { StudentAssessmentCard } from "@/components/lms/home/StudentAssessmentCard";
import { useErrorText } from "@/components/lms/home/useErrorText";

export function StudentAssessmentList() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const errorText = useErrorText();
  const base = `/${lang}/courses/${course.id}`;
  const [items, setItems] = useState<AssessmentStudentSummaryOut[]>([]);
  const [grades, setGrades] = useState<Record<string, MyGradeOut>>({});
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      // Grades only add the scheme value and the result link: a failure there must not hide the list.
      const [page, mine] = await Promise.all([
        listAssessments(course.id, { cursor: next, limit: 50 }),
        next ? Promise.resolve(null) : getMyGrades(course.id).catch(() => null),
      ]);
      const rows = page.items as AssessmentStudentSummaryOut[];
      setItems((p) => (next ? [...p, ...rows] : rows));
      if (mine) setGrades(Object.fromEntries(mine.items.map((g) => [g.assessment_id, g])));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id]);
  useEffect(() => { void load(); }, [load]);

  const rows = useMemo(() => {
    const now = Date.now();
    return items.map((a) => ({ a, v: studentAssessmentView(a, grades[a.id], now) }));
  }, [items, grades]);
  const primaryId = primaryAssessmentId(rows);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold leading-7 text-slate-900">{t("assessments.student.title")}</h2>
      {error && items.length === 0 ? (
        <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />
      ) : null}
      {error && items.length > 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} /> : null}
      {loading && items.length === 0 && !error && <LoadingState rows={3} />}
      {!loading && !error && items.length === 0 && (
        <EmptyState icon={<ClipboardList />} title={t("assessments.student.empty")} description={t("home.course.emptyHint")} />
      )}
      {rows.length > 0 && (
        <ul className="space-y-3">
          {rows.map(({ a, v }) => (
            <StudentAssessmentCard key={a.id} a={a} v={v} href={base} primary={a.id === primaryId}
              title={pickLocalized(a.title, lang, course.default_language) || t("assessments.untitled")} />
          ))}
        </ul>
      )}
      <Pagination nextCursor={cursor} loading={loading} onLoadMore={() => void load(cursor)} />
    </div>
  );
}
