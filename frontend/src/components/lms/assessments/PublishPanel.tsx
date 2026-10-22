"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { startPreview, validateAssessment } from "@/lib/lms/assessments";
import { previewAttemptId, type AssessmentStaffOut, type Issue } from "@/lib/lms/assessmentTypes";
import type { Lang } from "@/lib/lms/types";
import { btnPrimary, btnSecondary, inputCls } from "@/components/lms/content/ui";
import { AssessmentError } from "./AssessmentError";
import { IssueList, issuesFromDetails } from "./IssueList";
import { usePublishFlow } from "./usePublishFlow";

/** Validate, publish/unpublish and preview-as-student for the builder. */
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
  const flow = usePublishFlow(courseId, onChanged);
  const [validation, setValidation] = useState<{ errors: Issue[]; warnings: Issue[] } | null>(null);
  const [vBusy, setVBusy] = useState(false);
  const [vError, setVError] = useState<unknown>(null);
  const [pLang, setPLang] = useState<Lang>(a.languages[0]);
  const [pBusy, setPBusy] = useState(false);
  const [pError, setPError] = useState<unknown>(null);
  const [pIssues, setPIssues] = useState<Issue[]>([]);

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
    <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${published ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>{t(`assessments.status.${a.status}`)}</span>
        {a.current_version_no !== null && <span className="text-xs text-slate-500">{t("assessments.list.version", { n: a.current_version_no })}</span>}
        {published && a.has_unpublished_changes && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">{t("assessments.list.unpublishedChanges")}</span>}
        <span className="ml-auto flex flex-wrap items-center gap-2">
          {a.languages.length > 1 && (
            <select aria-label={t("assessments.publish.previewLanguage")} className={`${inputCls} w-auto`} value={pLang} onChange={(e) => setPLang(e.target.value as Lang)}>
              {a.languages.map((l) => <option key={l} value={l}>{t(`courses.languages.${l}`)}</option>)}
            </select>
          )}
          <button type="button" className={btnSecondary} disabled={pBusy} onClick={() => void preview()}>{pBusy ? t("lms.common.loading") : t("assessments.publish.preview")}</button>
          <button type="button" className={btnSecondary} disabled={vBusy} onClick={() => void validate()}>{vBusy ? t("lms.common.loading") : t("assessments.publish.validate")}</button>
          {canEdit && published && (
            <button type="button" className={btnSecondary} disabled={!!flow.busyId} onClick={() => void flow.unpublish(a.id)}>{t("assessments.publish.unpublish")}</button>
          )}
          {canEdit && (
            <button type="button" className={btnPrimary} disabled={!!flow.busyId} onClick={() => void flow.publish(a.id)}>
              {flow.busyId ? t("lms.common.loading") : published ? t("assessments.publish.republish") : t("assessments.publish.publish")}
            </button>
          )}
        </span>
      </div>
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
    </div>
  );
}
