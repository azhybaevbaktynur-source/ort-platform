"use client";

// Phase 7a S5: a student's Assignments tab (PHASE_7A_DESIGN 5): cards ordered by the effective due date, one primary
// action on the card that is next. In an ORT course this is the one exam card with the same Start flow (lobby).
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ClipboardList } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listAssignments } from "@/lib/lms/assignments";
import type { AssignmentStudentOut } from "@/lib/lms/assignmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { useTemplateUi } from "@/lib/lms/templates";
import { useCourse } from "@/components/lms/CourseContext";
import { EmptyState, ErrorState, LoadingState, Pagination } from "@/components/ui";
import { useAssignmentErrorText } from "./assignmentUi";
import { StudentAssignmentCard } from "./StudentAssignmentCard";
import { primaryAssignmentId, sortForStudent, studentAssignmentView } from "./studentAssignment";

export function StudentAssignmentList() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const ui = useTemplateUi();
  const errorText = useAssignmentErrorText();
  const readOnly = !!course.my_enrollment.read_only;
  const base = `/${lang}/courses/${course.id}`;
  const [items, setItems] = useState<AssignmentStudentOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listAssignments(course.id, { cursor: next, limit: 50 });
      const rows = page.items as AssignmentStudentOut[];
      setItems((p) => (next ? [...p, ...rows] : rows));
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
    return sortForStudent(items).map((a) => ({ a, v: studentAssignmentView(a, now, readOnly) }));
  }, [items, readOnly]);
  const primaryId = readOnly ? null : primaryAssignmentId(rows);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold leading-7 text-slate-900">{t("assignments.student.title")}</h2>
      {error && items.length === 0 ? <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} /> : null}
      {error && items.length > 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} /> : null}
      {loading && items.length === 0 && !error && <LoadingState rows={3} />}
      {!loading && !error && items.length === 0 && (
        <EmptyState icon={<ClipboardList />} title={t("assignments.student.empty")} description={t("assignments.student.emptyHint")} />
      )}
      {rows.length > 0 && (
        <ul className="space-y-3">
          {rows.map(({ a, v }) => (
            <StudentAssignmentCard key={a.id} a={a} v={v} base={base} primary={a.id === primaryId} ort={ui.key === "ort"}
              title={pickLocalized(a.title, lang, course.default_language) || t("assignments.untitled")} />
          ))}
        </ul>
      )}
      <Pagination nextCursor={cursor} loading={loading} onLoadMore={() => void load(cursor)} />
    </div>
  );
}
