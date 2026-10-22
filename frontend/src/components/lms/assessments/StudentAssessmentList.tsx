"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { listAssessments } from "@/lib/lms/assessments";
import type { AssessmentStudentSummaryOut } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { useCourse } from "@/components/lms/CourseContext";
import { Pager } from "@/components/lms/Pager";
import { btnPrimary, btnSecondary } from "@/components/lms/content/ui";
import { AssessmentError } from "./AssessmentError";
import { fmtDateTime, fmtPoints } from "./format";

export function StudentAssessmentList() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const base = `/${lang}/courses/${course.id}`;
  const [items, setItems] = useState<AssessmentStudentSummaryOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listAssessments(course.id, { cursor: next, limit: 50 });
      const rows = page.items as AssessmentStudentSummaryOut[];
      setItems((p) => (next ? [...p, ...rows] : rows));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id]);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-slate-900">{t("assessments.student.title")}</h2>
      <AssessmentError error={error} onRetry={error ? () => load() : undefined} />
      {loading && items.length === 0 && !error && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
      {!loading && !error && items.length === 0 && <p className="text-sm text-slate-500">{t("assessments.student.empty")}</p>}
      <ul className="space-y-3">
        {items.map((a) => {
          const title = pickLocalized(a.title, lang, course.default_language) || t("assessments.untitled");
          const unlimited = a.allowed_attempts === -1;
          return (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4">
              <div className="min-w-0 flex-1">
                <Link href={`${base}/assessments/${a.id}`} className="font-semibold text-slate-900 hover:text-brand-700">{title}</Link>
                <p className="mt-1 text-xs text-slate-500">
                  {t("assessments.student.items", { n: a.item_count })}
                  {a.time_limit_s ? ` · ${t("assessments.student.minutes", { n: Math.round(a.time_limit_s / 60) })}` : ""}
                  {" · "}{unlimited ? t("assessments.student.attemptsUnlimited", { used: a.attempts_used }) : t("assessments.student.attemptsOf", { used: a.attempts_used, total: a.allowed_attempts })}
                </p>
                {(a.available_from || a.available_until) && (
                  <p className="text-xs text-slate-400">
                    {a.available_from ? t("assessments.list.from", { date: fmtDateTime(a.available_from) }) : ""}
                    {a.available_from && a.available_until ? " · " : ""}
                    {a.available_until ? t("assessments.list.until", { date: fmtDateTime(a.available_until) }) : ""}
                  </p>
                )}
                {a.last_result && (
                  <p className="mt-1 text-xs font-medium text-emerald-700">
                    {t("assessments.student.lastResult", { score: fmtPoints(a.last_result.raw_score), total: fmtPoints(a.last_result.points_possible) })}
                  </p>
                )}
              </div>
              {a.in_progress_attempt_id ? (
                <Link href={`${base}/attempts/${a.in_progress_attempt_id}`} className={btnPrimary}>{t("assessments.student.resume")}</Link>
              ) : (
                <Link href={`${base}/assessments/${a.id}`} className={btnSecondary}>{t("assessments.student.open")}</Link>
              )}
            </li>
          );
        })}
      </ul>
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
    </div>
  );
}
