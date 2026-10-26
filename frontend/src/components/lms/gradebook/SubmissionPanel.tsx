"use client";

import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { CellOut, GradeRelease, SchemeLabelValue, SubmissionAttemptOut, SubmissionStaffOut } from "@/lib/lms/gradingTypes";
import { excuseSubmission, getSubmission, overrideSubmission, releaseGrades, unreleaseGrades } from "@/lib/lms/grading";
import { voidAttempt } from "@/lib/lms/staffAttempts";
import { useSchemeLabel } from "@/components/lms/grading/schemes/labels";
import { fmtNum, fmtPercentile, toNum } from "@/components/lms/grading/schemes/params";
import { SchemeError } from "@/components/lms/grading/schemes/SchemeError";
import { fmtDateTime } from "@/components/lms/assessments/format";
import { btnSecondary, btnSmall } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { cellFromSubmission, cellView, fmtPointsOf } from "./gradebookModel";
import { OverrideForm } from "./OverrideForm";
import { SubmissionAttempts } from "./SubmissionAttempts";
import { EventTimeline } from "./EventTimeline";
import { ReasonModal } from "./ReasonModal";
import { ManualWork } from "./ManualWork"; // Phase 7a S5
import type { AssignmentSubmissionStaffOut } from "@/lib/lms/assignmentTypes"; // Phase 7a S5

export interface PanelTarget {
  submissionId: string;
  enrollmentId: string;
  assessmentId: string;
  studentName: string;
  assessmentTitle: string;
  dueAt: string | null;
  /** the column scheme's label map (band key -> localized text) */
  labels?: Record<string, SchemeLabelValue> | null;
  /** the assessment's grade release mode: with "auto" a grade cannot be hidden (server 409 grade_release_auto) */
  gradeRelease?: GradeRelease;
  // --- Phase 7a S5 begin --- (`assessmentId` is the column id, i.e. the assignment id)
  kind?: "none" | "text" | "file" | "quiz";
  /** quiz columns: the assessment (attempt links) */
  quizAssessmentId?: string | null;
  // --- Phase 7a S5 end ---
}

type Dialog = null | { kind: "clear" } | { kind: "excuse"; excused: boolean } | { kind: "void"; attempt: SubmissionAttemptOut };
type Busy = "" | "override" | "clear" | "excuse" | "release" | "void";

/**
 * Side panel for one gradebook cell: kept result, counted attempts (with per-attempt grade and Void),
 * override with reason, excuse, per-submission release, and the grade-event history.
 * Every write sends the cell `version`; `grade_conflict` reloads the latest state.
 */
export function SubmissionPanel({
  courseId, target, canManage, onClose, onCell,
}: {
  courseId: string;
  target: PanelTarget;
  canManage: boolean;
  onClose: () => void;
  /** the cell changed (null: the submission no longer exists) */
  onCell: (enrollmentId: string, assessmentId: string, cell: CellOut | null) => void;
}) {
  const { lang, t } = useTranslation();
  const labelText = useSchemeLabel();
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [sub, setSub] = useState<SubmissionStaffOut | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [dialogError, setDialogError] = useState<unknown>(null);
  const [gone, setGone] = useState(false);
  const [busy, setBusy] = useState<Busy>("");
  const [dialog, setDialog] = useState<Dialog>(null);
  const seq = useRef(0);
  const { submissionId, enrollmentId, assessmentId } = target;

  const load = useCallback(async () => {
    const my = ++seq.current;
    try {
      const s = await getSubmission(courseId, submissionId);
      if (my !== seq.current) return null;
      setSub(s);
      setLoadError(null);
      return s;
    } catch (e) {
      if (my !== seq.current) return null;
      if ((e as { code?: string }).code === "submission_not_found") {
        setGone(true);
        onCell(enrollmentId, assessmentId, null);
      } else setLoadError(e);
      return null;
    }
  }, [courseId, submissionId, enrollmentId, assessmentId, onCell]);

  useEffect(() => {
    setSub(null); setGone(false); setLoadError(null); setActionError(null); setDialog(null);
    void load();
  }, [load]);
  useEffect(() => { closeRef.current?.focus(); }, [submissionId]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !dialog && !busy) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dialog, busy, onClose]);

  function applied(s: SubmissionStaffOut) {
    setSub(s);
    onCell(enrollmentId, assessmentId, cellFromSubmission(s));
  }

  /** Runs a write; on `grade_conflict` the latest state is reloaded and the error stays visible. */
  async function run(kind: Busy, fn: () => Promise<void>, inDialog: boolean) {
    setBusy(kind);
    setActionError(null);
    setDialogError(null);
    try {
      await fn();
      setDialog(null);
    } catch (e) {
      if ((e as { code?: string }).code === "grade_conflict") {
        setDialog(null);
        setActionError(e);
        const s = await load();
        if (s) onCell(enrollmentId, assessmentId, cellFromSubmission(s));
      } else if (inDialog) setDialogError(e);
      else setActionError(e);
    } finally {
      setBusy("");
    }
  }

  const saveOverride = (points: number, reason: string) =>
    run("override", async () => { if (sub) applied(await overrideSubmission(courseId, submissionId, { points, reason, version: sub.version })); }, false);
  const clearOverride = (reason: string) =>
    run("clear", async () => {
      if (sub) applied(await overrideSubmission(courseId, submissionId, { points: null, reason: reason || null, version: sub.version }));
    }, true);
  const setExcused = (excused: boolean, reason: string) =>
    run("excuse", async () => {
      if (sub) applied(await excuseSubmission(courseId, submissionId, { excused, reason: reason || null, version: sub.version }));
    }, true);
  const toggleRelease = (release: boolean) =>
    run("release", async () => {
      const body = { submission_ids: [submissionId] };
      if (release) await releaseGrades(courseId, assessmentId, body);
      else await unreleaseGrades(courseId, assessmentId, body);
      const s = await load();
      if (s) onCell(enrollmentId, assessmentId, cellFromSubmission(s));
    }, false);
  const doVoid = (attemptId: string, reason: string) =>
    run("void", async () => {
      await voidAttempt(courseId, attemptId, reason);
      const s = await load();
      if (s) onCell(enrollmentId, assessmentId, cellFromSubmission(s));
    }, true);

  // Phase 7a S5: attempt links use the quiz's assessment id (the column id is the assignment id)
  const attemptHref = (id: string) => `/${lang}/courses/${courseId}/assessments/${target.quizAssessmentId ?? assessmentId}/attempts/${id}`;
  const isQuiz = !target.kind || target.kind === "quiz";
  const v = sub ? cellView(sub, { due_at: target.dueAt, scheme: { labels: target.labels } }, Date.now()) : null;
  const excused = sub?.state === "excused";

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button type="button" aria-label={t("gradebook.close")} tabIndex={-1} onClick={() => { if (!busy && !dialog) onClose(); }}
        className="absolute inset-0 cursor-default bg-slate-900/30" />
      <aside role="dialog" aria-modal="true" aria-labelledby={titleId}
        className="relative flex h-full w-full max-w-md flex-col overflow-y-auto bg-white shadow-xl">
        <header className="sticky top-0 z-10 flex items-start gap-3 border-b border-slate-200 bg-white px-4 py-3">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="break-words text-base font-bold text-slate-900">{target.studentName}</h2>
            <p className="break-words text-sm text-slate-600">{target.assessmentTitle}</p>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} disabled={!!busy} aria-label={t("gradebook.close")}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-50">
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </header>

        <div className="flex-1 space-y-6 px-4 py-4">
          {gone && <p role="status" className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{t("gradebook.panel.gone")}</p>}
          {!gone && loadError ? <SchemeError error={loadError} onRetry={() => void load()} /> : null}
          {!gone && !sub && !loadError && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}

          {sub && v && !gone && (
            <>
              <section aria-label={t("gradebook.panel.summary")} className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                    v.kind === "needs_review" ? "bg-indigo-100 text-indigo-800" : v.kind === "excused" || v.kind === "no_attempts" ? "bg-slate-100 text-slate-700" : "bg-emerald-100 text-emerald-800"}`}>
                    {t(`gradebook.states.${v.kind}`)}
                  </span>
                  {v.overridden && <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-semibold text-violet-800">{t("gradebook.flags.overridden")}</span>}
                  {v.late && <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-semibold text-orange-800">{t("gradebook.flags.late")}</span>}
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${v.released ? "bg-sky-100 text-sky-800" : "bg-slate-100 text-slate-600"}`}>
                    {v.released ? t("gradebook.flags.released") : t("gradebook.flags.unreleased")}
                  </span>
                </div>
                {!excused && (v.value || v.label) && (
                  <p className="text-3xl font-bold text-slate-900">
                    {v.value}{v.value && v.label ? " · " : ""}{v.label ? labelText(v.label, v.labels) : ""}
                  </p>
                )}
                {v.thresholds.length > 0 && (
                  <p className="flex flex-wrap gap-1">
                    {v.thresholds.map((k) => <span key={k} className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">{labelText(k, v.labels)}</span>)}
                  </p>
                )}
                <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm text-slate-700">
                  <dt className="text-slate-500">{t("gradebook.panel.rawPoints")}</dt>
                  <dd>{fmtPointsOf(sub.raw_points, sub.points_possible) || "—"}</dd>
                  {sub.has_override && (<><dt className="text-slate-500">{t("gradebook.panel.override")}</dt><dd>{fmtNum(sub.override_points) || "—"}</dd></>)}
                  {(toNum(sub.late_deduction) ?? 0) > 0 && (<><dt className="text-slate-500">{t("gradebook.panel.lateDeduction")}</dt><dd>−{fmtNum(sub.late_deduction)}</dd></>)}
                  <dt className="text-slate-500">{t("gradebook.panel.effective")}</dt>
                  <dd className="font-semibold">{fmtPointsOf(sub.effective_points, sub.points_possible) || "—"}</dd>
                  {fmtPercentile(sub.percentile) && (<><dt className="text-slate-500">{t("gradebook.panel.percentile")}</dt><dd>{fmtPercentile(sub.percentile)}</dd></>)}
                  {isQuiz && (<><dt className="text-slate-500">{t("gradebook.panel.attemptsCounted")}</dt>
                  <dd>{sub.attempts_counted}</dd></>)}
                  {sub.released_at && (<><dt className="text-slate-500">{t("gradebook.panel.releasedAt")}</dt><dd>{fmtDateTime(sub.released_at)}</dd></>)}
                </dl>
                {sub.has_override && (
                  <div className="rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-sm text-violet-900">
                    <p>{sub.override_by_name || t("gradebook.events.system")}{sub.override_at ? ` · ${fmtDateTime(sub.override_at)}` : ""}</p>
                    {sub.override_reason && <p className="mt-1 whitespace-pre-wrap break-words"><span className="text-violet-700">{t("gradebook.events.reason")}:</span> {sub.override_reason}</p>}
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  {sub.kept_attempt_id && (
                    <Link href={attemptHref(sub.kept_attempt_id)} className="text-sm font-medium text-brand-700 hover:underline">{t("gradebook.panel.openKept")}</Link>
                  )}
                  {canManage && !(v.released && target.gradeRelease === "auto") && (
                    <button type="button" disabled={!!busy} onClick={() => void toggleRelease(!v.released)} className={btnSmall}>
                      {busy === "release" ? t("lms.common.loading") : v.released ? t("gradebook.panel.unrelease") : t("gradebook.panel.release")}
                    </button>
                  )}
                </div>
                {canManage && v.released && target.gradeRelease === "auto" && (
                  <p className="text-xs text-slate-500">{t("gradebook.panel.unreleaseAutoHint")}</p>
                )}
                <SchemeError error={actionError} />
              </section>

              {canManage && (
                <section aria-labelledby={`${titleId}-ov`} className="space-y-3 border-t border-slate-100 pt-4">
                  <h3 id={`${titleId}-ov`} className="text-sm font-bold text-slate-900">{t("gradebook.override.title")}</h3>
                  {/* the server rejects an override when every attempt is voided (422); excuse stays available */}
                  {sub.state !== "no_attempts" && (
                    <>
                      <p className="text-xs text-slate-500">{t("gradebook.override.hint")}</p>
                      <OverrideForm sub={sub} busy={busy === "override"} onSave={(p, r) => void saveOverride(p, r)} />
                    </>
                  )}
                  <div className="flex flex-wrap gap-2">
                    {sub.has_override && (
                      <button type="button" disabled={!!busy} onClick={() => { setDialogError(null); setDialog({ kind: "clear" }); }} className={btnSecondary}>
                        {t("gradebook.override.clear")}
                      </button>
                    )}
                    <button type="button" disabled={!!busy} onClick={() => { setDialogError(null); setDialog({ kind: "excuse", excused: !excused }); }} className={btnSecondary}>
                      {excused ? t("gradebook.excuse.unexcuse") : t("gradebook.excuse.excuse")}
                    </button>
                  </div>
                </section>
              )}

              {isQuiz ? (
                <section aria-labelledby={`${titleId}-at`} className="space-y-2 border-t border-slate-100 pt-4">
                  <h3 id={`${titleId}-at`} className="text-sm font-bold text-slate-900">{t("gradebook.panel.attempts")}</h3>
                  <SubmissionAttempts attempts={sub.attempts ?? []} labels={target.labels} keptAttemptId={sub.kept_attempt_id} attemptHref={attemptHref} canManage={canManage}
                    onVoid={(a) => { setDialogError(null); setDialog({ kind: "void", attempt: a }); }} />
                </section>
              ) : (
                /* Phase 7a S5: text / file / offline: hand-ins, rubric and feedback, graded on the grading screen */
                <ManualWork courseId={courseId} assignmentId={assessmentId} enrollmentId={enrollmentId} sub={sub as AssignmentSubmissionStaffOut} />
              )}

              <section aria-labelledby={`${titleId}-ev`} className="space-y-2 border-t border-slate-100 pt-4">
                <h3 id={`${titleId}-ev`} className="text-sm font-bold text-slate-900">{t("gradebook.events.title")}</h3>
                <EventTimeline events={sub.events} />
              </section>
            </>
          )}
        </div>
      </aside>

      <ReasonModal open={dialog?.kind === "clear"} optional title={t("gradebook.override.clearTitle")} body={t("gradebook.override.clearBody")}
        confirmLabel={t("gradebook.override.clear")} busy={busy === "clear"} error={dialogError}
        onConfirm={(r) => void clearOverride(r)} onCancel={() => setDialog(null)} />
      <ReasonModal open={dialog?.kind === "excuse"} optional
        title={dialog?.kind === "excuse" && !dialog.excused ? t("gradebook.excuse.unexcuseTitle") : t("gradebook.excuse.excuseTitle")}
        body={dialog?.kind === "excuse" && !dialog.excused ? t("gradebook.excuse.unexcuseBody") : t("gradebook.excuse.excuseBody")}
        confirmLabel={dialog?.kind === "excuse" && !dialog.excused ? t("gradebook.excuse.unexcuse") : t("gradebook.excuse.excuse")}
        busy={busy === "excuse"} error={dialogError}
        onConfirm={(r) => { if (dialog?.kind === "excuse") void setExcused(dialog.excused, r); }} onCancel={() => setDialog(null)} />
      <ReasonModal open={dialog?.kind === "void"} danger title={t("gradebook.void.title")}
        body={dialog?.kind === "void" && dialog.attempt.attempt_no !== null
          ? t("gradebook.void.bodyN", { n: dialog.attempt.attempt_no }) : t("gradebook.void.body")}
        confirmLabel={t("gradebook.void.confirm")} busy={busy === "void"} error={dialogError}
        onConfirm={(r) => { if (dialog?.kind === "void") void doVoid(dialog.attempt.id, r); }} onCancel={() => setDialog(null)} />
    </div>
  );
}
