"use client";

import React, { useState } from "react";
import { PencilLine } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { validateAssessment } from "@/lib/lms/assessments";
import type { Issue } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { AssessmentStatusBadge } from "@/components/lms/course/StaffCourseUi";
import { Badge, Button, ConfirmDialog } from "@/components/ui";
import { AssessmentError } from "@/components/lms/assessments/AssessmentError";
import { IssueList } from "@/components/lms/assessments/IssueList";
import { publishIsPrimary } from "@/components/lms/assessments/PublishPanel";
import { usePublishFlow } from "@/components/lms/assessments/usePublishFlow";
import { fmtPoints } from "@/components/lms/assessments/format";
import type { QuizCtx } from "./quizCtx";

const excerpt = (s: string) => s.replace(/\s+/g, " ").trim().slice(0, 80);

/**
 * Publish bar of the quiz editor (PHASE_7C_DESIGN 8.2, 8.6): sticky at the top with the status and Publish; the counts,
 * "Check" and "Unpublish" sit under it. Unfinished drafts are not part of the published quiz: the bar says so, and
 * publishing with drafts asks first (5.8, P7C-3).
 */
export function QuizPublishBar({ ctx, labels }: { ctx: QuizCtx; labels?: Map<string, string> }) {
  const { lang, t } = useTranslation();
  const { a, courseId, canEdit } = ctx;
  const flow = usePublishFlow(courseId, ctx.reload);
  const [validation, setValidation] = useState<{ errors: Issue[]; warnings: Issue[] } | null>(null);
  const [vBusy, setVBusy] = useState(false);
  const [vError, setVError] = useState<unknown>(null);
  const [confirmDrafts, setConfirmDrafts] = useState(false);
  const drafts = a.drafts ?? [];
  const published = a.status === "published";
  const title = pickLocalized(a.title, lang, a.languages[0]) || t("assessments.untitled");

  // The open card is closed first (a valid card is committed), so what is published is what the teacher sees.
  const closeOpenCard = async () => (ctx.closer.current ? ctx.closer.current("auto") : true);

  const check = async () => {
    if (!(await closeOpenCard())) return;
    setVBusy(true);
    setVError(null);
    try { setValidation(await validateAssessment(courseId, a.id)); } catch (e) { setVError(e); } finally { setVBusy(false); }
  };
  const publish = async () => {
    if (!(await closeOpenCard())) return;
    setValidation(null);
    if ((ctx.current().drafts ?? []).length > 0) { setConfirmDrafts(true); return; }
    await flow.publish(a.id);
  };

  const counts = `${t("quizEditor.publishBar.items", { n: a.item_count })} · ${t("quizEditor.publishBar.points", { n: fmtPoints(a.points_possible) || "0" })}`;
  const secondary = (
    <>
      <Button variant="secondary" size="sm" loading={vBusy} onClick={() => void check()}>{t("quizEditor.publishBar.check")}</Button>
      {canEdit && published && (
        <Button variant="secondary" size="sm" disabled={!!flow.busyId} onClick={() => flow.requestUnpublish(a.id, title, a.attempt_counts)}>
          {t("assessments.publish.unpublish")}
        </Button>
      )}
    </>
  );

  return (
    <section aria-label={t("teaching.publishPanel")} className="space-y-2">
      <div className="sticky top-0 z-20 rounded-2xl border border-slate-200 bg-white/95 px-3 py-2 shadow-sm backdrop-blur sm:px-4">
        <div className="flex flex-wrap items-center gap-2">
          <AssessmentStatusBadge status={a.status} />
          {published && a.has_unpublished_changes && <Badge tone="warning">{t("quizEditor.publishBar.unpublished")}</Badge>}
          <span className="hidden text-sm text-slate-600 sm:inline">{counts}</span>
          <div className="ml-auto flex items-center gap-2">
            <div className="hidden items-center gap-2 sm:flex">{secondary}</div>
            {canEdit && (
              <Button variant={publishIsPrimary(a) && a.item_count > 0 ? "primary" : "secondary"} size="sm" loading={!!flow.busyId} onClick={() => void publish()}>
                {published ? t("assessments.publish.republish") : t("quizEditor.publishBar.publish")}
              </Button>
            )}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:hidden">
        <span className="w-full text-sm text-slate-600">{counts}</span>
        {secondary}
      </div>
      {drafts.length > 0 && (
        <p role="note" className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <PencilLine className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{t("quizEditor.publishBar.unfinishedDrafts", { n: drafts.length })}</span>
        </p>
      )}
      <AssessmentError error={vError} />
      {validation && (
        validation.errors.length === 0 && validation.warnings.length === 0
          ? <p role="status" className="text-sm text-emerald-700">{t("assessments.publish.valid")}</p>
          : <div className="space-y-2">
              {validation.errors.length > 0 && <p className="text-sm font-semibold text-red-800">{t("assessments.publish.errors")}</p>}
              <IssueList issues={validation.errors} kind="error" />
              {validation.warnings.length > 0 && <p className="text-sm font-semibold text-amber-900">{t("assessments.publish.warnings")}</p>}
              <IssueList issues={validation.warnings} kind="warning" />
            </div>
      )}
      <AssessmentError error={flow.error} />
      <IssueList issues={flow.issues} kind="error" />
      {flow.unchanged && <p role="status" className="text-sm text-slate-600">{t("assessments.publish.unchanged")}</p>}
      {flow.dialog}
      <ConfirmDialog open={confirmDrafts} title={t("quizEditor.publishBar.draftsConfirmTitle")}
        effect={t("quizEditor.publishBar.unfinishedDrafts", { n: drafts.length })}
        confirmLabel={t("quizEditor.publishBar.publishAnyway")} busy={!!flow.busyId}
        onConfirm={() => { setConfirmDrafts(false); void flow.publish(a.id); }} onCancel={() => setConfirmDrafts(false)}>
        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-slate-700">
          {drafts.slice(0, 10).map((d) => (
            <li key={d.id} className="break-words">
              {t("quizEditor.publishBar.draftItem", {
                label: (d.item_id ? labels?.get(d.item_id) : undefined) ?? t("quizEditor.card.newQuestion"),
                text: excerpt(d.payload.stem) || t("quizEditor.card.emptyStem"),
              })}
            </li>
          ))}
        </ul>
      </ConfirmDialog>
    </section>
  );
}
