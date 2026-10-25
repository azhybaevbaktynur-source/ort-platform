"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { getStaffAttempt, voidAttempt, type AttemptStaffOut } from "@/lib/lms/staffAttempts";
import { getAssessment } from "@/lib/lms/assessments";
import { pickLocalized } from "@/lib/lms/localized";
import { useTabCrumbs } from "@/components/lms/course/StaffCourseUi";
import { Badge, Button, Checkbox, LoadingState, PageHeader } from "@/components/ui";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { ReasonModal } from "@/components/lms/gradebook/ReasonModal";
import { canVoid } from "@/components/lms/gradebook/gradebookModel";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { fmtDateTime, fmtPoints } from "@/components/lms/assessments/format";
import { ReviewItemCard } from "./ReviewItemCard";
import { GradeForm } from "./GradeForm";
import { ResultSummary } from "./ResultSummary";
import { GradeBadge } from "./GradeBadge";

export function StaffAttemptDetail({ courseId, assessmentId, attemptId }: { courseId: string; assessmentId: string; attemptId: string }) {
  const { lang, t } = useTranslation();
  const canGrade = true; // StaffGate already limits the page to teachers/assistants; the server enforces grades.manage
  const [data, setData] = useState<AttemptStaffOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [onlyPending, setOnlyPending] = useState(false);
  // write access mirrors the gradebook: teacher/assistant on a course that is not concluded (server enforces grades.manage)
  const canWrite = useCanEditContent();
  const [voidOpen, setVoidOpen] = useState(false);
  const [voidBusy, setVoidBusy] = useState(false);
  const [voidError, setVoidError] = useState<unknown>(null);

  const load = useCallback(async () => {
    try {
      setData(await getStaffAttempt(courseId, attemptId));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [courseId, attemptId]);
  useEffect(() => { void load(); }, [load]);
  // Phase 6b S5c: breadcrumbs Assessments > assessment > Attempts > student.
  const [aTitle, setATitle] = useState("");
  useEffect(() => {
    getAssessment(courseId, assessmentId)
      .then((a) => setATitle(pickLocalized(a.title, lang, a.languages?.[0] ?? lang) || t("assessments.untitled")))
      .catch(() => setATitle(t("assessments.untitled")));
  }, [courseId, assessmentId, lang, t]);

  async function doVoid(reason: string) {
    setVoidBusy(true);
    setVoidError(null);
    try {
      await voidAttempt(courseId, attemptId, reason);
      setVoidOpen(false);
      await load();
    } catch (e) {
      setVoidError(e);
    } finally {
      setVoidBusy(false);
    }
  }

  const abase = `/${lang}/courses/${courseId}/assessments/${assessmentId}`;
  const studentName = data ? data.student_name || t("grading.unnamed") : "";
  const crumbs = useTabCrumbs("assessments", [
    { label: aTitle || t("lms.common.loading"), href: abase },
    { label: t("grading.attemptsTitle"), href: `${abase}/attempts` },
    { label: studentName || t("lms.common.loading") },
  ], courseId);
  if (error && !data) return <div className="space-y-3"><PageHeader breadcrumbs={crumbs} title={t("grading.attemptsTitle")} className="mb-2" /><ErrorMessage error={error} onRetry={() => void load()} /></div>;
  if (!data) return <LoadingState rows={3} />;

  const submitted = data.status !== "in_progress" && data.status !== "void";
  // essays (pending) first, keeping document order inside each group
  const numbered = data.items.map((it, i) => ({ it, n: i + 1 }));
  const sorted = [...numbered].sort((a, b) => Number(b.it.correctness === "pending") - Number(a.it.correctness === "pending") || a.n - b.n);
  const shown = onlyPending ? sorted.filter((x) => x.it.correctness === "pending") : sorted;
  const attemptLabel = data.attempt_no ? t("grading.attemptN", { n: data.attempt_no }) : "";

  return (
    <div className="space-y-5">
      <PageHeader breadcrumbs={crumbs} title={studentName} className="mb-2"
        badge={data.is_preview ? <Badge tone="warning">{t("results.preview")}</Badge> : undefined}
        description={<>
          {t(`results.status.${data.status}`)}
          {attemptLabel ? ` · ${attemptLabel}` : ""}
          {data.submitted_at ? ` · ${fmtDateTime(data.submitted_at)}` : ""}
          {data.submit_reason ? ` · ${t(`grading.reason.${data.submit_reason}`)}` : ""}
        </>}
        secondaryActions={canWrite && canVoid(data) ? (
          <Button variant="secondary" className="border-danger-200 text-danger-700 hover:bg-danger-50" onClick={() => { setVoidError(null); setVoidOpen(true); }}>
            {t("gradebook.void.action")}
          </Button>
        ) : undefined} />
      <ErrorMessage error={error} onRetry={() => void load()} />
      {data.status === "needs_review" && (
        <p role="status" className="rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm text-indigo-900">{t("grading.needsReviewBanner", { n: data.pending_review })}</p>
      )}
      {data.status === "void" && (
        <p role="status" className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">{t("results.grade.voidedStaff")}</p>
      )}
      {data.result ? <ResultSummary result={data.result} grade={data.grade} /> : data.raw_score !== null && data.raw_score !== undefined ? (
        <p className="text-lg font-bold text-slate-900">{fmtPoints(data.raw_score)} / {fmtPoints(data.points_possible)}</p>
      ) : null}
      {!data.result && data.grade && <GradeBadge grade={data.grade} />}
      {!submitted && data.status !== "void" && <p className="text-sm text-slate-600">{t("grading.notSubmitted")}</p>}
      {data.pending_review > 0 && (
        <Checkbox label={t("grading.onlyPending")} checked={onlyPending} onChange={(e) => setOnlyPending(e.target.checked)} />
      )}
      <div className="space-y-4">
        {shown.map(({ it, n }) => {
          const max = it.points ?? it.question.points ?? null;
          const maxNum = max === null || max === undefined ? null : Number(max);
          return (
            <ReviewItemCard key={it.position} item={it} number={n} maxPoints={max} viewer="staff">
              {it.graded_at && (
                <p className="text-xs text-slate-500">
                  {t("grading.gradedBy", { name: it.graded_by_name || t("grading.unnamed"), date: fmtDateTime(it.graded_at) })}
                </p>
              )}
              {canGrade && submitted && (
                <GradeForm courseId={courseId} attemptId={attemptId} item={it}
                  max={maxNum !== null && Number.isFinite(maxNum) ? maxNum : null} onSaved={setData} />
              )}
            </ReviewItemCard>
          );
        })}
      </div>
      <ReasonModal open={voidOpen} danger title={t("gradebook.void.title")}
        object={attemptLabel ? `${studentName} · ${attemptLabel}` : studentName}
        body={data.attempt_no ? t("gradebook.void.bodyN", { n: data.attempt_no }) : t("gradebook.void.body")}
        confirmLabel={t("gradebook.void.confirm")} busy={voidBusy} error={voidError}
        onConfirm={(r) => void doVoid(r)} onCancel={() => setVoidOpen(false)} />
    </div>
  );
}
