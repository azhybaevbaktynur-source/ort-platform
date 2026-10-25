"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { getMyGrades } from "@/lib/lms/grading";
import type { MyGradeOut, MyGradesOut } from "@/lib/lms/gradingTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { SchemeError } from "@/components/lms/grading/schemes/SchemeError";
import { ScaleText } from "@/components/lms/grading/schemes/SchemeBadges";
import { fmtNum, fmtPercentile } from "@/components/lms/grading/schemes/params";
import { useSchemeLabel } from "@/components/lms/grading/schemes/labels";
import { fmtPoints } from "@/components/lms/assessments/format";
import { fmtShortDateTime } from "@/components/lms/home/format"; // Phase 7a UX: no seconds
import { useGradeText } from "./GradeBadge";
import { KindIcon, LateBadge } from "@/components/lms/assignments/assignmentUi"; // Phase 7a S5

const STATE_STYLE: Record<string, string> = {
  graded: "bg-emerald-100 text-emerald-800",
  pending: "bg-indigo-100 text-indigo-800",
  missing: "bg-slate-200 text-slate-700",
  excused: "bg-sky-100 text-sky-800",
  hidden: "bg-slate-200 text-slate-700",
  submitted: "bg-indigo-100 text-indigo-800", // Phase 7a S5
};

function Row({ item, courseId }: { item: MyGradeOut; courseId: string }) {
  const { lang, t } = useTranslation();
  const label = useSchemeLabel();
  const text = useGradeText();
  const flags = Object.entries(item.thresholds ?? {}).filter(([, on]) => on).map(([k]) => k);
  const pct = fmtPercentile(item.percentile);
  const graded = item.state === "graded";
  const main = graded ? text(item, item.scheme_type ?? undefined) : "";
  return (
    <li className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="break-words font-semibold text-slate-900">{pickLocalized(item.title, lang) || t("assessments.untitled")}</p>
          {item.due_at && <p className="text-xs text-slate-500">{t("results.grade.mine.due", { date: fmtShortDateTime(item.due_at, lang) })}</p>}
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATE_STYLE[item.state] ?? STATE_STYLE.hidden}`}>
          {item.state === "submitted" ? t("assignments.status.submitted") /* Phase 7a S5 */ : t(`results.grade.mine.state.${item.state}`)}
        </span>
      </div>
      {graded && (
        <div className="mt-2 space-y-1 text-sm">
          {main && <p className="text-2xl font-bold text-slate-900">{main}</p>}
          {item.effective_points !== null && item.effective_points !== undefined && item.points_possible !== null && item.points_possible !== undefined && (
            <p className="text-slate-600">{t("results.scoreOf", { score: fmtPoints(item.effective_points), max: fmtPoints(item.points_possible), count: fmtPoints(item.points_possible) })}</p>
          )}
          {item.late_deduction !== null && item.late_deduction !== undefined && Number(item.late_deduction) > 0 && (
            <p className="text-amber-800">{t("results.grade.mine.late", { n: fmtPoints(item.late_deduction) })}</p>
          )}
          <div className="flex flex-wrap gap-2">
            {pct && <span className="rounded-full bg-slate-100 px-2.5 py-0.5 font-medium text-slate-800">{t("results.grade.percentile", { value: pct })}</span>}
            {flags.map((k) => <span key={k} className="rounded-full bg-amber-100 px-2.5 py-0.5 font-semibold text-amber-900">{label(k, item.labels)}</span>)}
            {item.passed !== null && item.passed !== undefined && item.scheme_type !== "pass_fail" && (
              <span className={`rounded-full px-2.5 py-0.5 font-semibold ${item.passed ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"}`}>{label(item.passed ? "pass" : "fail")}</span>
            )}
          </div>
        </div>
      )}
      {item.state === "pending" && <p className="mt-2 text-sm text-slate-600">{t("results.grade.mine.pendingHint")}</p>}
      {/* --- Phase 7a S5: hand-in assignments (kind, handed in / late, feedback, link to the assignment) --- */}
      {item.kind && item.kind !== "quiz" && (
        <div className="mt-2 space-y-1 text-sm">
          <p className="flex flex-wrap items-center gap-2 text-slate-600">
            <span className="inline-flex items-center gap-1"><KindIcon kind={item.kind} />{t(`assignments.kinds.${item.kind}`)}</span>
            {item.submitted_at && <span>{t("assignments.myGrades.handedIn", { date: fmtShortDateTime(item.submitted_at, lang) })}</span>}
            {item.late && <LateBadge />}
          </p>
          {item.state === "submitted" && <p className="text-slate-600">{t("assignments.myGrades.waiting")}</p>}
          {graded && item.feedback_text && <p className="line-clamp-3 whitespace-pre-wrap break-words text-slate-800"><span className="font-semibold">{t("assignments.submit.feedback")}: </span>{item.feedback_text}</p>}
          {item.assignment_id && (
            <Link href={`/${lang}/courses/${courseId}/assignments/${item.assignment_id}`} className="inline-flex min-h-11 items-center font-medium text-brand-700 hover:underline sm:min-h-0">
              {graded ? t("assignments.myGrades.openFeedback") : t("assignments.myGrades.open")}
            </Link>
          )}
        </div>
      )}
      {/* --- Phase 7a S5 end --- */}
      {item.kept_attempt_id && graded && (
        <Link href={`/${lang}/courses/${courseId}/attempts/${item.kept_attempt_id}/result`} className="mt-2 inline-block text-sm font-medium text-brand-700 hover:underline">
          {t("results.grade.mine.viewResult")}
        </Link>
      )}
    </li>
  );
}

/** Student "My grades" page: states and numbers exactly as the server sends them. */
export function StudentGrades({ courseId }: { courseId: string }) {
  const { lang, t } = useTranslation();
  const text = useGradeText();
  const [data, setData] = useState<MyGradesOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => {
    try {
      setData(await getMyGrades(courseId));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [courseId]);
  useEffect(() => { void load(); }, [load]);

  if (error && !data) return <SchemeError error={error} onRetry={() => void load()} />;
  if (!data) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;

  const schemeType = data.scheme?.type;
  const total = data.total;
  // the total's label is a key of the course scheme: resolve it through the course scheme ref's labels
  const totalText = total ? text(total, schemeType, data.scheme?.labels) : "";
  const percent = total ? fmtNum(total.percent, 1) : "";
  // --- Phase 6 S6b begin --- (UX S7: no raw course percent next to a curve value such as the ORT score)
  // When every graded row uses a scheme of another type than the course total (e.g. ORT scaled scores under a
  // percent total), the total would show a second, smaller number for the same work: hide it.
  const gradedRows = data.items.filter((i) => i.state === "graded");
  const totalType = schemeType ?? "percent";
  const totalMisleading = gradedRows.length > 0 && gradedRows.every((i) => !!i.scheme_type && i.scheme_type !== totalType);
  // --- Phase 6 S6b end ---
  return (
    <div className="space-y-5">
      <h2 className="text-xl font-bold text-slate-900">{t("results.grade.mine.title")}</h2>
      <SchemeError error={error} onRetry={() => void load()} />
      {total && (totalText || percent) && !totalMisleading /* Phase 6 S6b */ && (
        <section className="rounded-2xl border border-brand-200 bg-brand-50 p-4" aria-label={t("results.grade.mine.total")}>
          <p className="text-xs font-medium text-brand-700">{t("results.grade.mine.total")}</p>
          <p className="break-words text-3xl font-bold text-slate-900">{totalText || `${percent}%`}</p>
          {totalText && percent && schemeType !== "percent" && <p className="text-sm text-slate-600">{percent}%</p>}
          {data.scheme && (
            <p className="mt-1 text-xs text-slate-600">
              {t("results.grade.mine.scheme", { title: pickLocalized(data.scheme.title, lang) || t(`schemes.types.${data.scheme.type}`) })}
              {" "}<ScaleText min={data.scheme.scale_min} max={data.scheme.scale_max} />
            </p>
          )}
          {total.passed !== null && total.passed !== undefined && schemeType !== "pass_fail" && (
            <p className="mt-1 text-sm font-semibold">{t(`schemes.labels.${total.passed ? "pass" : "fail"}`)}</p>
          )}
        </section>
      )}
      {data.items.length === 0 ? (
        <p className="text-sm text-slate-500">{t("results.grade.mine.empty")}</p>
      ) : (
        <ul className="space-y-3">
          {data.items.map((it) => <Row key={it.assignment_id ?? it.assessment_id ?? undefined} item={it} courseId={courseId} />)}
        </ul>
      )}
    </div>
  );
}
