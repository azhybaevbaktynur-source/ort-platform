"use client";

// Phase 6b S6b (UX S1): "My attempts" next to the lobby, so the result is reachable from where the student is.
// After the last attempt it comes first, with "No attempts left", and the lobby's notice becomes secondary.
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { listMyAttempts } from "@/lib/lms/attempts";
import type { MyAttemptOut } from "@/lib/lms/attemptTypes";
import { Badge, ErrorState, LinkButton, Skeleton, type BadgeTone } from "@/components/ui";
import { fmtPoints } from "@/components/lms/assessments/format";
import { useGradeListText } from "@/components/lms/results/GradeBadge";
import { parseApiDate } from "@/lib/format";
import { fmtShortDateTime } from "./format";
import { useErrorText } from "./useErrorText";

const TONE: Record<string, BadgeTone> = { in_progress: "info", submitted: "info", needs_review: "warning", graded: "success", void: "neutral" };

export function MyAttemptsPanel({ courseId, assessmentId, exhausted }: { courseId: string; assessmentId: string; exhausted: boolean }) {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const gradeText = useGradeListText();
  const [items, setItems] = useState<MyAttemptOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setItems(await listMyAttempts(courseId, assessmentId));
    } catch (e) {
      setError(e);
    }
  }, [courseId, assessmentId]);
  useEffect(() => { void load(); }, [load]);

  // newest first
  const done = (items ?? []).filter((a) => a.status !== "in_progress")
    .sort((x, y) => (parseApiDate(y.started_at)?.getTime() ?? 0) - (parseApiDate(x.started_at)?.getTime() ?? 0));
  if (!exhausted && items && done.length === 0) return null;

  return (
    // SF-1 (STUDENT_UI_FIX_PLAN §2.2 item 8): the attempts of this test as a list (student tokens)
    <section aria-labelledby="my-attempts" className="rounded-card border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <h2 id="my-attempts" className="text-base font-semibold leading-7 text-slate-900">{t("home.attempts.title")}</h2>
      {exhausted && <p className="mt-1 text-base font-semibold leading-6 text-slate-800">{t("home.noAttemptsLeft")}</p>}
      {exhausted && <p className="text-sm leading-6 text-slate-600">{t("home.attempts.exhaustedHint")}</p>}
      {error ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load()} className="mt-3" /> : null}
      {!items && !error && (
        <div aria-hidden="true" className="mt-3 space-y-2"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-5 w-1/2" /></div>
      )}
      {items && done.length === 0 && !error && <p className="mt-3 text-base leading-6 text-slate-600">{t("home.attempts.none")}</p>}
      {done.length > 0 && (
        <ul className="mt-2 divide-y divide-slate-100">
          {done.map((a, i) => {
            const r = a.result;
            const value = r?.grade ? gradeText({ ...r.grade, max_value: r.grade.scale_max ?? r.points_possible }) : r ? t("home.scoreOf", { score: fmtPoints(r.raw_score), total: fmtPoints(r.points_possible) }) : "";
            return (
              <li key={a.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 py-3 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-base font-semibold leading-6 text-slate-900">
                    {t("home.attempts.item", { n: a.attempt_no ?? done.length - i })}
                    <Badge tone={TONE[a.status] ?? "neutral"}>{t(`home.attempts.status.${a.status}`)}</Badge>
                  </p>
                  <p className="text-sm leading-6 text-slate-600">{fmtShortDateTime(a.submitted_at ?? a.started_at, lang)}</p>
                </div>
                <div className="text-right">
                  {value && a.results_available && <p className="whitespace-nowrap text-lg font-bold leading-7 tabular-nums text-slate-900">{value}</p>}
                  {!a.results_available && a.status !== "void" && <p className="text-sm leading-6 text-slate-600">{t("home.resultLater")}</p>}
                </div>
                {a.results_available && (
                  <LinkButton variant={exhausted && i === 0 ? "primary" : "secondary"} className="col-span-2 sm:col-span-1"
                    href={`/${lang}/courses/${courseId}/attempts/${a.id}/result`}>
                    {t("home.action.result")}
                  </LinkButton>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
