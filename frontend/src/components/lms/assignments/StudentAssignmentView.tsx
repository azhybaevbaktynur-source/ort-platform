"use client";

// Phase 7a S5: the student submit page (PHASE_7A_DESIGN 5): instructions (KaTeX), effective due date and window,
// status; text hand-in with a character count, or one file (PDF / JPG / PNG / WebP) with upload progress; one
// confirmation before handing in; earlier hand-ins; after grading the grade, the feedback and its file. States: not
// open yet, closed, already graded, offline (the text stays on this device; retry).
import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Download, FileText, Paperclip, Upload } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { getAssignment, handIn, openSubmissionFile, uploadHandInFile } from "@/lib/lms/assignments";
import {
  HAND_IN_ACCEPT, HAND_IN_IMAGE_MAX_BYTES, HAND_IN_MIME, HAND_IN_PDF_MAX_BYTES, HAND_IN_TEXT_MAX,
  isStaffAssignment, type AssignmentStudentDetailOut, type HandInOut,
} from "@/lib/lms/assignmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { useCourse } from "@/components/lms/CourseContext";
import { MathRenderer } from "@/components/math/MathRenderer";
import { useGradeText } from "@/components/lms/results/GradeBadge";
import { DueText } from "@/components/lms/home/StudentAssessmentCard";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { Button, Card, ConfirmDialog, ErrorState, LoadingState, PageHeader, Textarea, cn } from "@/components/ui";
import { AssignmentError, AssignmentStatusBadge, KindIcon, LateBadge, fmtBytes, fmtPts, useAssignmentErrorText } from "./assignmentUi";
import { studentAssignmentView } from "./studentAssignment";

const draftKey = (id: string) => `ort_assignment_draft_${id}`;
function readDraft(id: string): string {
  try { return localStorage.getItem(draftKey(id)) ?? ""; } catch { return ""; }
}
function writeDraft(id: string, text: string) {
  try {
    if (text) localStorage.setItem(draftKey(id), text);
    else localStorage.removeItem(draftKey(id));
  } catch { /* storage unavailable: the text stays in the page */ }
}

type FileIssue = "type" | "pdf_size" | "image_size" | null;
function fileIssue(f: File): FileIssue {
  if (!(HAND_IN_MIME as readonly string[]).includes(f.type)) return "type";
  if (f.type === "application/pdf" && f.size > HAND_IN_PDF_MAX_BYTES) return "pdf_size";
  if (f.type !== "application/pdf" && f.size > HAND_IN_IMAGE_MAX_BYTES) return "image_size";
  return null;
}

function HandInList({ items, courseId, submissionId }: { items: HandInOut[]; courseId: string; submissionId: string | null | undefined }) {
  const { lang, t } = useTranslation();
  const errorText = useAssignmentErrorText();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  if (items.length === 0) return null;
  const sorted = [...items].sort((a, b) => b.attempt_no - a.attempt_no);
  const download = async (h: HandInOut) => {
    if (!submissionId || !h.asset_id) return;
    setBusy(h.id);
    setError(null);
    try { await openSubmissionFile(courseId, submissionId, h.asset_id, h.filename); } catch (e) { setError(e); } finally { setBusy(null); }
  };
  return (
    <Card title={t("assignments.submit.previous")} headingLevel={2}>
      <ol className="space-y-3">
        {sorted.map((h) => (
          <li key={h.id} className="rounded-xl border border-slate-200 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-slate-900">{t("assignments.submit.handInN", { n: h.attempt_no })}</span>
              <span className="text-sm text-slate-600">{fmtShortDateTime(h.submitted_at, lang)}</span>
              {(h.late ?? h.late_seconds > 0) && <LateBadge />}
            </div>
            {h.kind === "text" && h.body_text && (
              <p className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-2 text-base leading-6 text-slate-800 sm:text-sm">{h.body_text}</p>
            )}
            {h.kind === "file" && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="inline-flex min-w-0 items-center gap-1.5 break-all text-sm text-slate-800"><Paperclip aria-hidden="true" className="h-4 w-4 shrink-0" />{h.filename || t("assignments.submit.file")}</span>
                {h.bytes ? <span className="text-sm text-slate-600">{fmtBytes(h.bytes, t)}</span> : null}
                {submissionId && h.asset_id && (
                  <Button variant="secondary" size="sm" loading={busy === h.id} leftIcon={<Download aria-hidden="true" className="h-4 w-4" />} onClick={() => void download(h)}>
                    {t("assignments.submit.download")}<span className="sr-only">: {h.filename}</span>
                  </Button>
                )}
              </div>
            )}
          </li>
        ))}
      </ol>
      {error ? <p role="alert" className="mt-3 text-sm text-danger-700">{errorText(error)}</p> : null}
    </Card>
  );
}

export function StudentAssignmentView({ assignmentId }: { assignmentId: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const gradeText = useGradeText();
  const errorText = useAssignmentErrorText();
  const readOnly = !!course.my_enrollment.read_only;
  const base = `/${lang}/courses/${course.id}`;
  const [a, setA] = useState<AssignmentStudentDetailOut | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileProblem, setFileProblem] = useState<FileIssue>(null);
  const [uploaded, setUploaded] = useState<{ name: string; asset_id: string } | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [feedbackError, setFeedbackError] = useState<unknown>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const out = await getAssignment(course.id, assignmentId);
      if (isStaffAssignment(out)) { router.replace(`${base}/assignments/${assignmentId}/edit`); return; }
      if (out.kind === "quiz" && out.assessment_id) { router.replace(`${base}/assessments/${out.assessment_id}`); return; }
      setA(out);
    } catch (e) {
      setLoadError(e);
    }
  }, [course.id, assignmentId, router, base]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setText(readDraft(assignmentId)); }, [assignmentId]);

  if (loadError && !a) {
    const missing = (loadError as { status?: number }).status === 404;
    return (
      <div className="space-y-4">
        <Link href={`${base}/assignments`} className="inline-flex min-h-11 items-center text-sm font-medium text-brand-700 hover:underline sm:min-h-0">{t("assignments.backToList")}</Link>
        <ErrorState title={missing ? t("assignments.submit.notFoundTitle") : undefined} message={errorText(loadError)} onRetry={missing ? undefined : () => void load()} />
      </div>
    );
  }
  if (!a) return <LoadingState rows={2} />;

  const v = studentAssignmentView(a);
  const title = pickLocalized(a.title, lang, course.default_language) || t("assignments.untitled");
  const description = pickLocalized(a.description, lang, course.default_language);
  const status = a.status ?? "not_started";
  const graded = status === "graded";
  // the server decides (window, graded latest hand-in, file limit, course state); the client checks only add to it
  const canHandIn = !readOnly && a.can_hand_in && (a.kind === "text" || a.kind === "file") && !v.opensLater && !v.windowClosed && !graded && status !== "excused";
  const resubmit = a.hand_ins.length > 0;
  const textTooLong = text.length > HAND_IN_TEXT_MAX;
  const ready = a.kind === "text" ? !!text.trim() && !textTooLong : !!(file && !fileProblem) || !!uploaded;
  const offline = (error as { code?: string } | null)?.code === "network";

  const pick = (f: File | null) => {
    setFile(f);
    setUploaded(null);
    setProgress(null);
    setError(null);
    setFileProblem(f ? fileIssue(f) : null);
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (a.kind === "text") {
        await handIn(course.id, a.id, { body_text: text });
        writeDraft(a.id, "");
        setText("");
      } else {
        let asset = uploaded;
        if (!asset && file) {
          setProgress(0);
          const up = await uploadHandInFile(course.id, a.id, file, (r) => setProgress(r));
          asset = { name: up.filename || file.name, asset_id: up.asset_id };
          setUploaded(asset);
        }
        if (!asset) return;
        await handIn(course.id, a.id, { asset_id: asset.asset_id });
        setFile(null);
        setUploaded(null);
        if (inputRef.current) inputRef.current.value = "";
      }
      setConfirming(false);
      setDone(true);
      await load();
    } catch (e) {
      setConfirming(false);
      setError(e);
    } finally {
      setBusy(false);
      setProgress(null);
    }
  };

  const g = a.grade;
  // the grade row id: on the released grade, else on every hand-in
  const submissionId = g?.submission_id ?? a.hand_ins[0]?.submission_id ?? null;
  const openFeedback = async () => {
    if (!submissionId || !g?.feedback_asset_id) return;
    setFeedbackBusy(true);
    setFeedbackError(null);
    try { await openSubmissionFile(course.id, submissionId, g.feedback_asset_id); } catch (e) { setFeedbackError(e); } finally { setFeedbackBusy(false); }
  };

  const gradeValue = g ? gradeText(g) : "";
  const points = g && g.points !== null && g.points !== undefined ? fmtPts(g.points) : "";

  let closedNote: string | null = null;
  if (!readOnly && (a.kind === "text" || a.kind === "file")) {
    if (v.opensLater && a.available_from) closedNote = t("assignments.submit.notOpen", { date: fmtShortDateTime(a.available_from, lang) });
    else if (graded) closedNote = t("assignments.submit.alreadyGraded");
    else if (v.windowClosed) closedNote = a.available_until ? t("assignments.submit.closedOn", { date: fmtShortDateTime(a.available_until, lang) }) : t("assignments.submit.closed");
    else if (a.reason === "already_graded") closedNote = t("assignments.submit.gradedNotReleased");
    else if (a.reason === "limit_reached") closedNote = t("assignments.submit.limitReached");
    else if (a.reason === "course_not_active") closedNote = t("assignments.submit.notActive");
    else if (a.reason === "closed" || a.reason === "not_open_yet") closedNote = t("assignments.submit.closed");
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-5">
      <Link href={`${base}/assignments`} className="inline-flex min-h-11 items-center text-sm font-medium text-brand-700 hover:underline sm:min-h-0">{t("assignments.backToList")}</Link>
      <PageHeader title={title} className="mb-0" badge={a.status ? <AssignmentStatusBadge status={status} /> : undefined}>
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm leading-6 text-slate-600">
          <li className="inline-flex items-center gap-1"><KindIcon kind={a.kind} />{t(`assignments.kinds.${a.kind}`)}</li>
          {a.due_at && <li><DueText value={a.due_at} lang={lang} /></li>}
          {a.available_from && v.opensLater && <li>{t("home.opens", { date: fmtShortDateTime(a.available_from, lang) })}</li>}
          {a.available_until && !v.windowClosed && <li>{t("home.until", { date: fmtShortDateTime(a.available_until, lang) })}</li>}
          {fmtPts(a.points_possible) && <li>{t("assignments.student.points", { n: fmtPts(a.points_possible) })}</li>}
        </ul>
      </PageHeader>

      {graded && g && (
        <Card title={t("assignments.submit.gradeTitle")} headingLevel={2} className="border-success-200">
          {gradeValue && <p className="text-3xl font-bold leading-9 text-slate-900">{gradeValue}</p>}
          {points && <p className="text-base text-slate-700">{t("assignments.submit.pointsOf", { points, possible: fmtPts(g.points_possible) || "—" })}</p>}
          {g.late_deduction && Number(g.late_deduction) > 0 ? <p className="text-sm text-warning-900">{t("results.grade.mine.late", { n: fmtPts(g.late_deduction) })}</p> : null}
          {g.feedback_text && (
            <div className="mt-3">
              <h3 className="text-sm font-semibold text-slate-900">{t("assignments.submit.feedback")}</h3>
              <p className="mt-1 whitespace-pre-wrap break-words text-base leading-6 text-slate-800 sm:text-sm">{g.feedback_text}</p>
            </div>
          )}
          {g.feedback_asset_id && submissionId && (
            <div className="mt-3">
              <Button variant="secondary" loading={feedbackBusy} leftIcon={<Download aria-hidden="true" className="h-4 w-4" />} onClick={() => void openFeedback()}>
                {t("assignments.submit.feedbackFile")}
              </Button>
              {feedbackError ? <p role="alert" className="mt-2 text-sm text-danger-700">{errorText(feedbackError)}</p> : null}
            </div>
          )}
        </Card>
      )}
      {status === "submitted" && !done && a.reason !== "already_graded" && <p role="status" className="rounded-xl border border-brand-200 bg-brand-50 px-3 py-2 text-base text-brand-800 sm:text-sm">{t("assignments.submit.waiting")}</p>}
      {done && <p role="status" className="rounded-xl border border-success-200 bg-success-50 px-3 py-2 text-base text-success-800 sm:text-sm">{t("assignments.submit.handedIn")}</p>}

      <Card title={t("assignments.submit.instructions")} headingLevel={2}>
        {description ? <MathRenderer content={description} className="whitespace-pre-line break-words text-base sm:text-sm" />
          : <p className="text-base text-slate-600 sm:text-sm">{a.kind === "none" ? t("assignments.submit.noneHint") : t("assignments.submit.noInstructions")}</p>}
        {a.kind === "none" && description ? <p className="mt-3 text-sm text-slate-600">{t("assignments.submit.noneHint")}</p> : null}
      </Card>

      {closedNote && <p role="status" className="rounded-xl border border-slate-200 bg-slate-100 px-3 py-2 text-base text-slate-700 sm:text-sm">{closedNote}</p>}

      {canHandIn && (
        <Card title={resubmit ? t("assignments.submit.again") : t("assignments.submit.title")} headingLevel={2}
          description={resubmit ? t("assignments.submit.againHint") : undefined}>
          {a.kind === "text" ? (
            <Textarea label={t("assignments.submit.textLabel")} rows={10} value={text}
              onChange={(e) => { setText(e.target.value); writeDraft(a.id, e.target.value); }}
              hint={t("assignments.submit.count", { n: text.length, max: HAND_IN_TEXT_MAX })}
              error={textTooLong ? t("assignments.submit.tooLong", { max: HAND_IN_TEXT_MAX }) : undefined} />
          ) : (
            <div className="space-y-3">
              <label className={cn("flex min-h-11 cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center hover:bg-slate-100", "focus-within:ring-2 focus-within:ring-brand-600")}>
                <Upload aria-hidden="true" className="h-6 w-6 text-slate-600" />
                <span className="text-base font-semibold text-brand-700 sm:text-sm">{file ? t("assignments.submit.changeFile") : t("assignments.submit.chooseFile")}</span>
                <span className="text-sm text-slate-600">{t("assignments.submit.fileLimits")}</span>
                <input ref={inputRef} type="file" accept={HAND_IN_ACCEPT} className="sr-only" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
              </label>
              {file && (
                <p className="flex flex-wrap items-center gap-2 text-sm text-slate-800">
                  <FileText aria-hidden="true" className="h-4 w-4 shrink-0" /><span className="break-all font-medium">{file.name}</span>
                  <span className="text-slate-600">{fmtBytes(file.size, t)}</span>
                </p>
              )}
              {fileProblem && <p role="alert" className="text-sm text-danger-700">{t(`assignments.submit.fileIssue.${fileProblem}`)}</p>}
              {progress !== null && (
                <div role="progressbar" aria-label={t("assignments.submit.uploading")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200"><div className="h-2 rounded-full bg-brand-600 transition-all" style={{ width: `${Math.round(progress * 100)}%` }} /></div>
                  <p className="mt-1 text-sm text-slate-600">{t("assignments.submit.uploadingN", { n: Math.round(progress * 100) })}</p>
                </div>
              )}
            </div>
          )}
          {error && !confirming ? (
            offline ? (
              <ErrorState variant="inline" className="mt-3" title={t("assignments.submit.offlineTitle")} message={t("assignments.submit.offlineBody")} onRetry={() => void submit()} retrying={busy} />
            ) : <AssignmentError error={error} className="mt-3" />
          ) : null}
          <div className="sticky bottom-3 z-10 mt-4 rounded-2xl border border-slate-200 bg-white p-3 shadow-lg sm:static sm:border-0 sm:bg-transparent sm:p-0 sm:shadow-none">
            <Button className="w-full sm:w-auto" disabled={!ready || busy} onClick={() => setConfirming(true)}>{t("assignments.submit.handIn")}</Button>
          </div>
        </Card>
      )}

      <HandInList items={a.hand_ins ?? []} courseId={course.id} submissionId={submissionId} />

      <ConfirmDialog open={confirming} busy={busy} title={t("assignments.submit.confirmTitle")} object={title}
        effect={a.kind === "file" ? t("assignments.submit.confirmFile", { name: uploaded?.name ?? file?.name ?? "" }) : t("assignments.submit.confirmText", { n: text.length })}
        confirmLabel={t("assignments.submit.handIn")} onConfirm={() => void submit()} onCancel={() => setConfirming(false)}
        error={error && confirming ? errorText(error) : undefined} />
      <p className="sr-only" aria-live="polite">{busy ? t("assignments.submit.sending") : ""}</p>
    </div>
  );
}
