"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { startPreview, validateAssessment } from "@/lib/lms/assessments";
import { previewAttemptId, type AssessmentStaffOut, type Issue } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { AssessmentStatusBadge } from "@/components/lms/course/StaffCourseUi";
import { Badge, Button } from "@/components/ui";
import type { Lang } from "@/lib/lms/types";
import { inputCls } from "@/components/lms/content/ui";
import { AssessmentError } from "./AssessmentError";
import { IssueList, issuesFromDetails } from "./IssueList";
import { usePublishFlow } from "./usePublishFlow";
// --- Phase 7b S4 begin --- (PHASE_7B_DESIGN 10: template badge, upgrade, import format, "Save as template")
import { TemplateBadge } from "@/components/lms/examTemplates/TemplateBadge";
import { SaveAsTemplateDialog } from "@/components/lms/examTemplates/SaveAsTemplateDialog";
// --- Phase 7b S4 end ---

/** True when publishing is the next step (a draft, or published with unpublished changes): the page's one primary action. */
export function publishIsPrimary(a: Pick<AssessmentStaffOut, "status" | "has_unpublished_changes">): boolean {
  return a.status !== "published" || a.has_unpublished_changes;
}

/**
 * Validate, publish/unpublish and preview-as-student for the builder.
 * Phase 6b S5c (UX T8): the publish button is primary only when publishing is the next step (else secondary),
 * "Check before publishing" names validation, and unpublishing with attempts asks first (T6).
 */
export function PublishPanel({
  assessment, courseId, canEdit, onChanged,
}: {
  assessment: AssessmentStaffOut;
  courseId: string;
  canEdit: boolean;
  onChanged: () => void | Promise<void>;
}) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const a = assessment;
  const title = pickLocalized(a.title, lang, a.languages[0]) || t("assessments.untitled");
  const flow = usePublishFlow(courseId, onChanged);
  const [validation, setValidation] = useState<{ errors: Issue[]; warnings: Issue[] } | null>(null);
  const [vBusy, setVBusy] = useState(false);
  const [vError, setVError] = useState<unknown>(null);
  const [pLang, setPLang] = useState<Lang>(a.languages[0]);
  const [pBusy, setPBusy] = useState(false);
  const [pError, setPError] = useState<unknown>(null);
  const [pIssues, setPIssues] = useState<Issue[]>([]);
  // Phase 7b S4: preset (ORT) exams are never templatable (7b-Q1), so ORT builders show no "Save as template".
  const [saveAsOpen, setSaveAsOpen] = useState(false);
  // Phase 7b S6 (decision L5): a structure fixed by a locked template is never copied into a new template.
  const templatable = canEdit && a.preset === "none" && !a.structure_locked && !a.exam_template?.template_locked;

  const validate = async () => {
    setVBusy(true);
    setVError(null);
    try { setValidation(await validateAssessment(courseId, a.id)); } catch (e) { setVError(e); } finally { setVBusy(false); }
  };
  const preview = async () => {
    setPBusy(true);
    setPError(null);
    setPIssues([]);
    try {
      const out = await startPreview(courseId, a.id, a.languages.includes(pLang) ? pLang : a.languages[0]);
      const id = previewAttemptId(out);
      if (id) router.push(`/${lang}/courses/${courseId}/attempts/${id}`);
      else setPError({ code: "unknown" });
    } catch (e) {
      setPError(e);
      setPIssues(issuesFromDetails((e as { details?: unknown }).details));
    } finally {
      setPBusy(false);
    }
  };

  const published = a.status === "published";
  return (
    <section aria-label={t("teaching.publishPanel")} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <AssessmentStatusBadge status={a.status} />
          {a.current_version_no !== null && <span className="text-sm text-slate-600">{t("assessments.list.version", { n: a.current_version_no })}</span>}
          {published && a.has_unpublished_changes && <Badge tone="warning">{t("assessments.list.unpublishedChanges")}</Badge>}
        </div>
        <div className="flex w-full flex-wrap items-center gap-2 sm:ml-auto sm:w-auto sm:justify-end [&>*]:flex-1 sm:[&>*]:flex-none">
          {a.languages.length > 1 && (
            <select aria-label={t("assessments.publish.previewLanguage")} className={`${inputCls} min-h-11 w-auto sm:min-h-9`} value={pLang} onChange={(e) => setPLang(e.target.value as Lang)}>
              {a.languages.map((l) => <option key={l} value={l}>{t(`courses.languages.${l}`)}</option>)}
            </select>
          )}
          <Button variant="secondary" size="sm" loading={pBusy} onClick={() => void preview()}>{t("assessments.publish.preview")}</Button>
          <Button variant="secondary" size="sm" loading={vBusy} onClick={() => void validate()}>{t("assessments.publish.validate")}</Button>
          {templatable && <Button variant="secondary" size="sm" onClick={() => setSaveAsOpen(true)}>{t("examTemplates.saveAs.action")}</Button>}
          {canEdit && published && (
            <Button variant="secondary" size="sm" disabled={!!flow.busyId} onClick={() => flow.requestUnpublish(a.id, title, a.attempt_counts)}>{t("assessments.publish.unpublish")}</Button>
          )}
          {canEdit && (
            <Button variant={publishIsPrimary(a) ? "primary" : "secondary"} size="sm" loading={!!flow.busyId} onClick={() => void flow.publish(a.id)}>
              {published ? t("assessments.publish.republish") : t("assessments.publish.publish")}
            </Button>
          )}
        </div>
      </div>
      {/* --- Phase 7b S4 --- */}
      {a.exam_template && <TemplateBadge assessment={a} courseId={courseId} canEdit={canEdit} onChanged={onChanged} />}
      {templatable && <SaveAsTemplateDialog open={saveAsOpen} assessment={a} courseId={courseId} onClose={() => setSaveAsOpen(false)} />}
      <AssessmentError error={pError} />
      <IssueList issues={pIssues} kind="error" />
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
      {a.warnings.length > 0 && !validation && <IssueList issues={a.warnings as Issue[]} kind="warning" />}
      <AssessmentError error={flow.error} />
      <IssueList issues={flow.issues} kind="error" />
      {flow.unchanged && <p role="status" className="text-sm text-slate-600">{t("assessments.publish.unchanged")}</p>}
      {flow.dialog}
    </section>
  );
}
