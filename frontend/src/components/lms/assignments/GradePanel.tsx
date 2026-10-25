"use client";

// Phase 7a S5: grade one student's work (PHASE_7A_DESIGN 3.6, 5): hand-ins (text shown, files to download), rubric
// scores with their sum, points, feedback text and an optional feedback file, save with the optimistic version
// (409 stale_grade reloads the latest state), release / hide for this student, clear the grade.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Paperclip, Upload, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  getAssignmentSubmission, gradeManual, openSubmissionFile, releaseAssignmentGrades, unreleaseAssignmentGrades, uploadFeedbackFile,
} from "@/lib/lms/assignments";
import {
  FEEDBACK_TEXT_MAX, HAND_IN_ACCEPT, type AssignmentStaffOut, type AssignmentSubmissionRowOut, type AssignmentSubmissionStaffOut,
} from "@/lib/lms/assignmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { Badge, Button, Card, ConfirmDialog, IconButton, Input, LoadingState, Textarea, toast } from "@/components/ui";
import { AssignmentError, LateBadge, fmtBytes, fmtPts, parsePoints, useAssignmentErrorText } from "./assignmentUi";

interface ScoreRow { points: string; comment: string }

export function GradePanel({
  courseId, assignment, row, defaultLanguage, canManage, onChanged, onPrev, onNext,
}: {
  courseId: string;
  assignment: AssignmentStaffOut;
  row: AssignmentSubmissionRowOut;
  defaultLanguage: Lang;
  canManage: boolean;
  /** the grade row changed: refresh the roster row */
  onChanged: (sub: AssignmentSubmissionStaffOut | null) => void;
  onPrev?: () => void;
  onNext?: () => void;
}) {
  const { lang, t } = useTranslation();
  const errorText = useAssignmentErrorText();
  const rubric = useMemo(() => [...(assignment.rubric ?? [])].sort((a, b) => a.position - b.position), [assignment.rubric]);
  const hasRubric = rubric.length > 0;
  const [sub, setSub] = useState<AssignmentSubmissionStaffOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [points, setPoints] = useState("");
  const [scores, setScores] = useState<Record<string, ScoreRow>>({});
  const [feedback, setFeedback] = useState("");
  const [feedbackAsset, setFeedbackAsset] = useState<{ id: string; name: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState<"" | "save" | "release" | "clear">("");
  const [error, setError] = useState<unknown>(null);
  const [clearing, setClearing] = useState(false);
  const [touched, setTouched] = useState(false);
  const submissionId = row.cell?.submission_id ?? null;

  const seed = useCallback((s: AssignmentSubmissionStaffOut | null) => {
    setSub(s);
    setPoints(s && s.raw_points !== null && s.raw_points !== undefined ? fmtPts(s.raw_points) : "");
    const next: Record<string, ScoreRow> = {};
    for (const c of rubric) {
      const sc = s?.rubric_scores?.find((x) => x.criterion_id === c.id);
      next[c.id] = { points: sc ? fmtPts(sc.points) : "", comment: sc?.comment ?? "" };
    }
    setScores(next);
    setFeedback(s?.feedback_text ?? "");
    setFeedbackAsset(s?.feedback_asset_id ? { id: s.feedback_asset_id, name: t("assignments.grade.feedbackFile") } : null);
    setTouched(false);
  }, [rubric, t]);

  const load = useCallback(async () => {
    setLoadError(null);
    setError(null);
    if (!submissionId) { seed(null); return; }
    setLoading(true);
    try {
      seed(await getAssignmentSubmission(courseId, submissionId));
    } catch (e) {
      setLoadError(e);
    } finally {
      setLoading(false);
    }
  }, [courseId, submissionId, seed]);
  useEffect(() => { void load(); }, [load, row.enrollment_id]);

  const parsedScores = rubric.map((c) => parsePoints(scores[c.id]?.points ?? ""));
  const scoreBad = rubric.map((c, i) => {
    const p = parsedScores[i];
    return p === null || Number.isNaN(p) || p < 0 || p > Number(c.points);
  });
  const rubricSum = parsedScores.reduce<number>((s, p) => s + (p && !Number.isNaN(p) ? p : 0), 0);
  const possible = Number(assignment.points_possible ?? 0);
  const pts = hasRubric ? Math.round(rubricSum * 100) / 100 : parsePoints(points);
  const pointsBad = pts === null || Number.isNaN(pts) || pts < 0 || pts > possible;
  const valid = !pointsBad && (!hasRubric || !scoreBad.some(Boolean)) && feedback.length <= FEEDBACK_TEXT_MAX;

  const save = async () => {
    setTouched(true);
    if (!valid || pts === null) return;
    setBusy("save");
    setError(null);
    try {
      const out = await gradeManual(courseId, assignment.id, row.enrollment_id, {
        points: pts,
        ...(hasRubric ? { rubric_scores: rubric.map((c, i) => ({ criterion_id: c.id, points: parsedScores[i] as number, comment: scores[c.id]?.comment.trim() || null })) } : {}),
        feedback_text: feedback.trim() || null,
        // absent = unchanged (the server accepts only files the grader uploaded; another grader keeps the old one)
        ...((feedbackAsset?.id ?? null) !== (sub?.feedback_asset_id ?? null) ? { feedback_asset_id: feedbackAsset?.id ?? null } : {}),
        ...(sub ? { version: sub.version } : {}),
      });
      seed(out);
      onChanged(out);
      toast.success(t("assignments.grade.saved"));
    } catch (e) {
      if ((e as { code?: string }).code === "stale_grade" || (e as { code?: string }).code === "grade_conflict") {
        toast.error(t("assignments.errors.stale_grade"));
        await load();
      } else setError(e);
    } finally {
      setBusy("");
    }
  };

  const clear = async () => {
    setBusy("clear");
    setError(null);
    try {
      const out = await gradeManual(courseId, assignment.id, row.enrollment_id, { points: null, ...(sub ? { version: sub.version } : {}) });
      seed(out);
      onChanged(out);
      setClearing(false);
    } catch (e) {
      setError(e);
      setClearing(false);
    } finally {
      setBusy("");
    }
  };

  const toggleRelease = async (release: boolean) => {
    if (!sub) return;
    setBusy("release");
    setError(null);
    try {
      const body = { submission_ids: [sub.submission_id] };
      if (release) await releaseAssignmentGrades(courseId, assignment.id, body);
      else await unreleaseAssignmentGrades(courseId, assignment.id, body);
      const s = await getAssignmentSubmission(courseId, sub.submission_id);
      seed(s);
      onChanged(s);
    } catch (e) {
      setError(e);
    } finally {
      setBusy("");
    }
  };

  const uploadFeedback = async (f: File | null) => {
    if (!f) return;
    setUploading(true);
    setError(null);
    try {
      const up = await uploadFeedbackFile(courseId, assignment.id, f);
      setFeedbackAsset({ id: up.asset_id, name: up.filename || f.name });
    } catch (e) {
      setError(e);
    } finally {
      setUploading(false);
    }
  };

  const download = async (assetId: string, name?: string | null) => {
    if (!submissionId) return;
    try { await openSubmissionFile(courseId, submissionId, assetId, name); } catch (e) { setError(e); }
  };

  const graded = sub?.state === "graded" && sub.raw_points !== null && sub.raw_points !== undefined;
  const released = !!sub?.released_at;
  const handIns = [...(sub?.hand_ins ?? [])].sort((a, b) => b.attempt_no - a.attempt_no);
  const student = row.student_name || t("gradebook.unnamed");

  return (
    <Card as="section" aria-label={t("assignments.grade.panelFor", { name: student })}
      title={student}
      description={row.latest_submitted_at ? t("assignments.grade.handedInAt", { date: fmtShortDateTime(row.latest_submitted_at, lang) }) : t("assignments.grade.noHandIn")}
      actions={(onPrev || onNext) ? (
        <span className="inline-flex gap-1">
          <IconButton variant="secondary" aria-label={t("assignments.grade.prev")} icon={<ChevronLeft />} disabled={!onPrev} onClick={onPrev} />
          <IconButton variant="secondary" aria-label={t("assignments.grade.next")} icon={<ChevronRight />} disabled={!onNext} onClick={onNext} />
        </span>
      ) : undefined}>
      {loading && !sub ? <LoadingState rows={1} /> : loadError ? <AssignmentError error={loadError} onRetry={() => void load()} /> : (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2">
            {graded ? <Badge tone="success">{t("assignments.status.graded")}</Badge> : row.hand_in_count > 0 ? <Badge tone="info">{t("assignments.grade.needsGrading")}</Badge> : null}
            {row.resubmitted && <Badge tone="warning">{t("assignments.grade.resubmitted")}</Badge>}
            {row.late && <LateBadge />}
            {graded && <Badge tone={released ? "info" : "neutral"}>{released ? t("gradebook.flags.released") : t("gradebook.flags.unreleased")}</Badge>}
          </div>

          {assignment.kind !== "none" && (
            <section aria-label={t("assignments.grade.handIns")} className="space-y-2">
              <h3 className="text-sm font-semibold text-slate-900">{t("assignments.grade.handIns")}</h3>
              {handIns.length === 0 ? <p className="text-sm text-slate-600">{t("assignments.grade.noHandIn")}</p> : (
                <ol className="space-y-2">
                  {handIns.map((h) => (
                    <li key={h.id} className="rounded-xl border border-slate-200 p-3">
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="font-semibold text-slate-900">{t("assignments.submit.handInN", { n: h.attempt_no })}</span>
                        <span className="text-slate-600">{fmtShortDateTime(h.submitted_at, lang)}</span>
                        {(h.late ?? h.late_seconds > 0) && <LateBadge />}
                        {sub?.graded_item_id === h.id && <Badge tone="success">{t("assignments.grade.gradedThis")}</Badge>}
                      </div>
                      {h.kind === "text" && h.body_text && (
                        <p className="mt-2 max-h-72 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-2 text-base leading-6 text-slate-800 sm:text-sm">{h.body_text}</p>
                      )}
                      {h.kind === "file" && h.asset_id && (
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <span className="inline-flex min-w-0 items-center gap-1.5 break-all text-sm"><Paperclip aria-hidden="true" className="h-4 w-4 shrink-0" />{h.filename || t("assignments.submit.file")}</span>
                          {h.bytes ? <span className="text-sm text-slate-600">{fmtBytes(h.bytes, t)}</span> : null}
                          <Button variant="secondary" size="sm" leftIcon={<Download aria-hidden="true" className="h-4 w-4" />} onClick={() => void download(h.asset_id!, h.filename)}>
                            {t("assignments.submit.download")}
                          </Button>
                        </div>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </section>
          )}

          {canManage && (
            <section aria-label={t("assignments.grade.gradeSection")} className="space-y-4 border-t border-slate-100 pt-4">
              {hasRubric && (
                <fieldset className="space-y-3">
                  <legend className="text-sm font-semibold text-slate-900">{t("assignments.rubric.title")}</legend>
                  {rubric.map((c, i) => (
                    <div key={c.id} className="rounded-xl border border-slate-200 p-3">
                      <p className="text-sm font-medium text-slate-900">{pickLocalized(c.title, lang, defaultLanguage) || t("assignments.rubric.criterion", { n: i + 1 })}</p>
                      <div className="mt-2 grid gap-3 sm:grid-cols-[8rem_minmax(0,1fr)]">
                        <Input label={t("assignments.grade.criterionPoints", { max: fmtPts(c.points) })} inputMode="decimal"
                          value={scores[c.id]?.points ?? ""} onChange={(e) => setScores((s) => ({ ...s, [c.id]: { ...(s[c.id] ?? { comment: "" }), points: e.target.value } }))}
                          error={touched && scoreBad[i] ? t("assignments.grade.criterionInvalid", { max: fmtPts(c.points) }) : undefined} />
                        <Input label={t("assignments.grade.comment")} optional maxLength={1000}
                          value={scores[c.id]?.comment ?? ""} onChange={(e) => setScores((s) => ({ ...s, [c.id]: { ...(s[c.id] ?? { points: "" }), comment: e.target.value } }))} />
                      </div>
                    </div>
                  ))}
                  <p className="text-sm font-medium text-slate-800" aria-live="polite">{t("assignments.grade.rubricSum", { sum: fmtPts(rubricSum), possible: fmtPts(possible) })}</p>
                </fieldset>
              )}
              {!hasRubric && (
                <Input label={t("assignments.grade.points", { max: fmtPts(possible) })} inputMode="decimal" value={points}
                  onChange={(e) => setPoints(e.target.value)} containerClassName="sm:max-w-xs"
                  error={touched && pointsBad ? t("assignments.grade.pointsInvalid", { max: fmtPts(possible) }) : undefined} />
              )}
              {hasRubric && touched && pointsBad && <p className="text-sm text-danger-700">{t("assignments.grade.pointsInvalid", { max: fmtPts(possible) })}</p>}
              <Textarea label={t("assignments.grade.feedback")} optional rows={4} value={feedback} maxLength={FEEDBACK_TEXT_MAX}
                onChange={(e) => setFeedback(e.target.value)} hint={t("assignments.grade.feedbackHint")} />
              <div className="space-y-2">
                {feedbackAsset ? (
                  <p className="flex flex-wrap items-center gap-2 text-sm text-slate-800">
                    <Paperclip aria-hidden="true" className="h-4 w-4 shrink-0" /><span className="break-all">{feedbackAsset.name}</span>
                    {sub?.feedback_asset_id === feedbackAsset.id && (
                      <Button variant="link" onClick={() => void download(feedbackAsset.id)}>{t("assignments.submit.download")}</Button>
                    )}
                    <IconButton aria-label={t("assignments.grade.removeFile")} icon={<X />} onClick={() => setFeedbackAsset(null)} />
                  </p>
                ) : (
                  <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 shadow-sm hover:bg-slate-50 focus-within:ring-2 focus-within:ring-brand-600">
                    <Upload aria-hidden="true" className="h-4 w-4" />{uploading ? t("assignments.submit.uploading") : t("assignments.grade.attachFile")}
                    <input type="file" accept={HAND_IN_ACCEPT} className="sr-only" disabled={uploading} onChange={(e) => void uploadFeedback(e.target.files?.[0] ?? null)} />
                  </label>
                )}
              </div>
              <AssignmentError error={error} />
              <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap [&>*]:w-full sm:[&>*]:w-auto">
                <Button loading={busy === "save"} disabled={!!busy || uploading} onClick={() => void save()}>{t("assignments.grade.save")}</Button>
                {graded && assignment.grade_release === "manual" && (
                  <Button variant="secondary" loading={busy === "release"} disabled={!!busy} onClick={() => void toggleRelease(!released)}>
                    {released ? t("gradebook.panel.unrelease") : t("gradebook.panel.release")}
                  </Button>
                )}
                {graded && <Button variant="link" disabled={!!busy} onClick={() => setClearing(true)}>{t("assignments.grade.clear")}</Button>}
              </div>
              {sub?.graded_at && (
                <p className="text-sm text-slate-600">{t("assignments.grade.gradedBy", { name: sub.graded_by_name || "—", date: fmtShortDateTime(sub.graded_at, lang) })}</p>
              )}
            </section>
          )}
        </div>
      )}
      <ConfirmDialog open={clearing} tone="danger" busy={busy === "clear"} title={t("assignments.grade.clearTitle")} object={student}
        effect={t("assignments.grade.clearBody")} confirmLabel={t("assignments.grade.clear")}
        onConfirm={() => void clear()} onCancel={() => setClearing(false)} error={error && clearing ? errorText(error) : undefined} />
    </Card>
  );
}
