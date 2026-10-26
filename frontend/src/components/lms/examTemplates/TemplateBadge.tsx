"use client";

// Phase 7b S4: builder header line of an exam created from a template (PHASE_7B_DESIGN 10): "From template <title>
// v<n>", "Newer version available · Upgrade" (draft without attempts, confirm dialog, issues listed after) and the
// import-format CSV download.
import React, { useState } from "react";
import { Download, LayoutTemplate } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { downloadImportFormat, upgradeAssessmentTemplate } from "@/lib/lms/examTemplates";
import type { AssessmentStaffOut, Issue } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { Button, ConfirmDialog, toast } from "@/components/ui";
import { IssueList, issuesFromDetails } from "@/components/lms/assessments/IssueList";
import { ExamTemplateError, useExamTemplateErrorText } from "./ui";

export function TemplateBadge({ assessment, courseId, canEdit, onChanged }: {
  assessment: AssessmentStaffOut;
  courseId: string;
  canEdit: boolean;
  onChanged: () => void | Promise<void>;
}) {
  const { lang, t } = useTranslation();
  const errText = useExamTemplateErrorText();
  const a = assessment;
  const ref = a.exam_template;
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [dlBusy, setDlBusy] = useState(false);
  const [dlError, setDlError] = useState<unknown>(null);
  if (!ref) return null;

  const tplTitle = pickLocalized(ref.title, lang) || t("examTemplates.untitled");
  const examTitle = pickLocalized(a.title, lang, a.languages[0]) || t("assessments.untitled");
  const newer = ref.latest_version_no != null && ref.latest_version_no > ref.version_no;
  const noAttempts = a.attempt_counts.in_progress + a.attempt_counts.submitted === 0;
  const canUpgrade = canEdit && newer && a.status === "draft" && noAttempts;

  const upgrade = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await upgradeAssessmentTemplate(courseId, a.id);
      const found = out.issues ?? [];
      setIssues(found);
      setConfirm(false);
      toast.success(t("examTemplates.upgrade.done", { n: ref.latest_version_no ?? ref.version_no }));
      await onChanged();
    } catch (e) {
      setError(e);
      setIssues(issuesFromDetails((e as { details?: unknown }).details));
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    setDlBusy(true);
    setDlError(null);
    try {
      await downloadImportFormat(ref.template_id, ref.version_no, lang);
      toast.success(t("examTemplates.importFormat.downloaded"));
    } catch (e) {
      setDlError(e);
    } finally {
      setDlBusy(false);
    }
  };

  return (
    <div className="space-y-2 rounded-xl border border-brand-100 bg-brand-50/60 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <p className="flex min-w-0 items-start gap-2 text-sm text-slate-800">
          <LayoutTemplate className="mt-0.5 h-4 w-4 shrink-0 text-brand-700" aria-hidden="true" />
          <span className="break-words">{t("examTemplates.badge.from", { title: tplTitle, n: ref.version_no })}</span>
        </p>
        {newer && (
          <p className="text-sm font-medium text-warning-900">
            {t("examTemplates.badge.newer", { n: ref.latest_version_no ?? 0 })}
          </p>
        )}
        <div className="flex w-full flex-wrap gap-2 sm:ml-auto sm:w-auto [&>*]:flex-1 sm:[&>*]:flex-none">
          {canUpgrade && <Button variant="secondary" size="sm" onClick={() => { setError(null); setConfirm(true); }}>{t("examTemplates.upgrade.action")}</Button>}
          <Button variant="secondary" size="sm" loading={dlBusy} leftIcon={<Download className="h-4 w-4" aria-hidden="true" />} onClick={() => void download()}>
            {t("examTemplates.importFormat.download")}
          </Button>
        </div>
      </div>
      {newer && !canUpgrade && canEdit && <p className="text-sm text-slate-600">{t("examTemplates.upgrade.notAllowed")}</p>}
      <ExamTemplateError error={dlError} onRetry={() => void download()} />
      {issues.length > 0 && !confirm && (
        <div className="space-y-1">
          <p className="text-sm font-semibold text-amber-900">{t("examTemplates.upgrade.issues")}</p>
          <IssueList issues={issues} kind="warning" />
        </div>
      )}
      <ConfirmDialog
        open={confirm}
        title={t("examTemplates.upgrade.title")}
        object={examTitle}
        effect={t("examTemplates.upgrade.effect", { from: ref.version_no, to: ref.latest_version_no ?? ref.version_no })}
        confirmLabel={t("examTemplates.upgrade.confirm")}
        cancelLabel={t("ui.cancel")}
        busy={busy}
        error={error ? errText(error) : undefined}
        onConfirm={() => void upgrade()}
        onCancel={() => setConfirm(false)}
      >
        {issues.length > 0 && <IssueList issues={issues} kind="error" />}
      </ConfirmDialog>
    </div>
  );
}
