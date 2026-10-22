"use client";

import React, { useCallback, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { isLmsApiError } from "@/lib/lms/client";
import { publishAssessment, unpublishAssessment } from "@/lib/lms/assessments";
import type { ConfirmRequiredDetails, Issue } from "@/lib/lms/assessmentTypes";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { issuesFromDetails } from "./IssueList";

/**
 * Publish / unpublish with the server-side "teacher warned" flow (P3-9):
 * 409 confirm_required opens a dialog and re-sends with confirm=true;
 * 422 publish_invalid exposes the issue list.
 */
export function usePublishFlow(courseId: string, onChanged: () => void | Promise<void>) {
  const { t } = useTranslation();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [unchanged, setUnchanged] = useState(false);
  const [confirm, setConfirm] = useState<{ id: string; inProgress: number; submitted: number } | null>(null);

  const run = useCallback(async (id: string, confirmed: boolean) => {
    setBusyId(id);
    setError(null);
    setIssues([]);
    setUnchanged(false);
    try {
      const out = await publishAssessment(courseId, id, confirmed);
      setConfirm(null);
      setUnchanged(out.unchanged);
      await onChanged();
    } catch (e) {
      if (isLmsApiError(e) && e.code === "confirm_required") {
        const d = (e.details ?? {}) as Partial<ConfirmRequiredDetails>;
        setConfirm({ id, inProgress: Number(d.in_progress ?? 0), submitted: Number(d.submitted ?? 0) });
      } else if (isLmsApiError(e) && e.code === "publish_invalid") {
        setConfirm(null);
        setIssues(issuesFromDetails(e.details));
        setError(e);
      } else {
        setConfirm(null);
        setError(e);
      }
    } finally {
      setBusyId(null);
    }
  }, [courseId, onChanged]);

  const publish = useCallback((id: string) => run(id, false), [run]);

  const unpublish = useCallback(async (id: string) => {
    setBusyId(id);
    setError(null);
    setIssues([]);
    setUnchanged(false);
    try {
      await unpublishAssessment(courseId, id);
      await onChanged();
    } catch (e) {
      setError(e);
    } finally {
      setBusyId(null);
    }
  }, [courseId, onChanged]);

  const dialog = (
    <ConfirmDialog open={!!confirm} busy={!!busyId} title={t("assessments.publish.confirmTitle")}
      body={confirm ? t("assessments.publish.confirmBody", { inProgress: confirm.inProgress, submitted: confirm.submitted }) : undefined}
      confirmLabel={t("assessments.publish.confirmAction")}
      onConfirm={() => confirm && void run(confirm.id, true)} onCancel={() => setConfirm(null)} />
  );

  return { busyId, error, issues, unchanged, publish, unpublish, dialog, clear: () => { setError(null); setIssues([]); setUnchanged(false); } };
}
