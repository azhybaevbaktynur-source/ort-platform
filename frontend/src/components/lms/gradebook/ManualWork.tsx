"use client";

// Phase 7a S5: the non-quiz part of the gradebook submission panel: hand-ins, rubric scores and feedback (read-only);
// grading itself happens on the assignment's grading screen.
import React, { useState } from "react";
import { Download, Paperclip } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { openSubmissionFile } from "@/lib/lms/assignments";
import type { AssignmentSubmissionStaffOut } from "@/lib/lms/assignmentTypes";
import { Button, LinkButton } from "@/components/ui";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { LateBadge, useAssignmentErrorText } from "@/components/lms/assignments/assignmentUi";

export function ManualWork({ courseId, assignmentId, enrollmentId, sub }: {
  courseId: string;
  assignmentId: string;
  enrollmentId: string;
  sub: AssignmentSubmissionStaffOut;
}) {
  const { lang, t } = useTranslation();
  const errorText = useAssignmentErrorText();
  const [error, setError] = useState<unknown>(null);
  const handIns = [...(sub.hand_ins ?? [])].sort((a, b) => b.attempt_no - a.attempt_no);
  const open = async (assetId: string, name?: string | null) => {
    setError(null);
    try { await openSubmissionFile(courseId, sub.submission_id, assetId, name); } catch (e) { setError(e); }
  };
  return (
    <section aria-label={t("assignments.grade.handIns")} className="space-y-3 border-t border-slate-100 pt-4">
      <h3 className="text-sm font-bold text-slate-900">{t("assignments.grade.handIns")}</h3>
      {handIns.length === 0 ? <p className="text-sm text-slate-600">{t("assignments.grade.noHandIn")}</p> : (
        <ol className="space-y-2">
          {handIns.map((h) => (
            <li key={h.id} className="rounded-xl border border-slate-200 p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-900">{t("assignments.submit.handInN", { n: h.attempt_no })}</span>
                <span className="text-slate-600">{fmtShortDateTime(h.submitted_at, lang)}</span>
                {(h.late ?? h.late_seconds > 0) && <LateBadge />}
              </div>
              {h.kind === "text" && h.body_text && <p className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap break-words text-slate-800">{h.body_text}</p>}
              {h.kind === "file" && h.asset_id && (
                <Button variant="link" className="mt-1" leftIcon={<Paperclip aria-hidden="true" className="h-4 w-4" />} onClick={() => void open(h.asset_id!, h.filename)}>
                  {h.filename || t("assignments.submit.file")}
                </Button>
              )}
            </li>
          ))}
        </ol>
      )}
      {(sub.rubric_scores ?? []).length > 0 && (
        <p className="text-sm text-slate-700">{t("assignments.gradebook.rubricScored", { n: sub.rubric_scores.length })}</p>
      )}
      {sub.feedback_text && (
        <div>
          <h4 className="text-sm font-semibold text-slate-900">{t("assignments.submit.feedback")}</h4>
          <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-800">{sub.feedback_text}</p>
        </div>
      )}
      {sub.feedback_asset_id && (
        <Button variant="link" leftIcon={<Download aria-hidden="true" className="h-4 w-4" />} onClick={() => void open(sub.feedback_asset_id!)}>
          {t("assignments.submit.feedbackFile")}
        </Button>
      )}
      {sub.graded_at && <p className="text-xs text-slate-500">{t("assignments.grade.gradedBy", { name: sub.graded_by_name || "—", date: fmtShortDateTime(sub.graded_at, lang) })}</p>}
      {error ? <p role="alert" className="text-sm text-danger-700">{errorText(error)}</p> : null}
      <LinkButton variant="secondary" href={`/${lang}/courses/${courseId}/assignments/${assignmentId}/grade?enrollment=${encodeURIComponent(enrollmentId)}`}>
        {t("assignments.gradebook.openGrading")}
      </LinkButton>
    </section>
  );
}
