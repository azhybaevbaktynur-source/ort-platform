"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { listStaffAttempts, type AttemptStaffSummaryOut } from "@/lib/lms/staffAttempts";
import type { AttemptStatus } from "@/lib/lms/attemptTypes";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Pager } from "@/components/lms/Pager";
import { inputCls } from "@/components/lms/content/ui";
import { fmtDateTime, fmtPoints } from "@/components/lms/assessments/format";

const STATUSES: AttemptStatus[] = ["in_progress", "needs_review", "graded", "void"];
const LIMIT = 50;

export function StaffAttemptList({ courseId, assessmentId }: { courseId: string; assessmentId: string }) {
  const { lang, t } = useTranslation();
  const [status, setStatus] = useState<AttemptStatus | "">("");
  const [previews, setPreviews] = useState(false);
  const [rows, setRows] = useState<AttemptStaffSummaryOut[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    try {
      const page = await listStaffAttempts(courseId, assessmentId, { status, preview: previews, limit: LIMIT });
      if (my !== seq.current) return;
      setRows(page.items);
      setNext(page.next_cursor);
      setError(null);
    } catch (e) {
      if (my === seq.current) setError(e);
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }, [courseId, assessmentId, status, previews]);
  useEffect(() => { void load(); }, [load]);

  async function loadMore() {
    if (!next) return;
    setMore(true);
    try {
      const page = await listStaffAttempts(courseId, assessmentId, { status, preview: previews, cursor: next, limit: LIMIT });
      setRows((r) => [...r, ...page.items]);
      setNext(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setMore(false);
    }
  }

  const base = `/${lang}/courses/${courseId}/assessments/${assessmentId}`;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href={base} className="text-sm font-medium text-brand-700 hover:underline">{t("grading.backToAssessment")}</Link>
          <h2 className="mt-1 text-xl font-bold text-slate-900">{t("grading.attemptsTitle")}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <span>{t("grading.filterStatus")}</span>
            <select value={status} onChange={(e) => setStatus(e.target.value as AttemptStatus | "")} className={`${inputCls} w-auto`}>
              <option value="">{t("grading.allStatuses")}</option>
              {STATUSES.map((s) => <option key={s} value={s}>{t(`results.status.${s}`)}</option>)}
            </select>
          </label>
          <button type="button" onClick={() => setStatus(status === "needs_review" ? "" : "needs_review")} aria-pressed={status === "needs_review"}
            className={`rounded-xl border px-3 py-2 text-sm font-medium ${status === "needs_review" ? "border-indigo-400 bg-indigo-50 text-indigo-800" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"}`}>
            {t("grading.needsReviewOnly")}
          </button>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={previews} onChange={(e) => setPreviews(e.target.checked)} />
            {t("grading.showPreviews")}
          </label>
        </div>
      </div>
      <ErrorMessage error={error} onRetry={() => void load()} />
      {loading ? (
        <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>
      ) : rows.length === 0 && !error ? (
        <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{t("grading.empty")}</p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                <th className="px-4 py-2 font-medium">{t("grading.student")}</th>
                <th className="px-4 py-2 font-medium">{t("grading.attemptNo")}</th>
                <th className="px-4 py-2 font-medium">{t("grading.status")}</th>
                <th className="px-4 py-2 font-medium">{t("grading.submitted")}</th>
                <th className="px-4 py-2 font-medium">{t("grading.score")}</th>
                <th className="px-4 py-2 font-medium"><span className="sr-only">{t("grading.open")}</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2 font-medium text-slate-900">
                    {r.student_name || t("grading.unnamed")}
                    {r.is_preview && <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">{t("results.preview")}</span>}
                  </td>
                  <td className="px-4 py-2">{r.attempt_no ?? "—"}</td>
                  <td className="px-4 py-2">
                    <span>{t(`results.status.${r.status}`)}</span>
                    {r.pending_review > 0 && <span className="ml-2 rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-semibold text-indigo-800">{t("grading.pendingBadge", { n: r.pending_review })}</span>}
                  </td>
                  <td className="px-4 py-2 text-slate-600">{fmtDateTime(r.submitted_at) || "—"}</td>
                  <td className="px-4 py-2">{r.raw_score !== null && r.raw_score !== undefined ? `${fmtPoints(r.raw_score)} / ${fmtPoints(r.points_possible)}` : "—"}</td>
                  <td className="px-4 py-2 text-right">
                    <Link href={`${base}/attempts/${r.id}`} className="font-medium text-brand-700 hover:underline">{t("grading.open")}</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pager nextCursor={next} loading={more} onMore={() => void loadMore()} />
    </div>
  );
}
