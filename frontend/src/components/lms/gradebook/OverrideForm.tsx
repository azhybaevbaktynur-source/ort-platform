"use client";

import React, { useEffect, useId, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { SubmissionStaffOut } from "@/lib/lms/gradingTypes";
import { btnPrimary, inputCls } from "@/components/lms/content/ui";
import { fmtNum } from "@/components/lms/grading/schemes/params";
import { checkOverride, REASON_MAX, type OverrideIssue } from "./gradebookModel";

/** Set a manual score with a required reason. Clearing is a separate action (panel). */
export function OverrideForm({
  sub, busy, onSave,
}: {
  sub: SubmissionStaffOut;
  busy: boolean;
  onSave: (points: number, reason: string) => void;
}) {
  const { t } = useTranslation();
  const pid = useId();
  const rid = useId();
  const [points, setPoints] = useState("");
  const [reason, setReason] = useState("");
  const [issues, setIssues] = useState<OverrideIssue[]>([]);
  useEffect(() => { setPoints(""); setReason(""); setIssues([]); }, [sub.submission_id, sub.version]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const r = checkOverride(points, reason, sub.points_possible);
    setIssues(r.issues);
    if (r.issues.length === 0 && r.points !== null) onSave(r.points, reason.trim());
  }

  const max = fmtNum(sub.points_possible);
  const pointsIssue = issues.find((i) => i.startsWith("points_"));
  const reasonIssue = issues.find((i) => i.startsWith("reason_"));
  return (
    <form onSubmit={submit} className="space-y-2" noValidate>
      <div>
        <label htmlFor={pid} className="mb-1 block text-sm font-medium text-slate-700">
          {max ? t("gradebook.override.pointsMax", { max }) : t("gradebook.override.points")}
        </label>
        <input id={pid} inputMode="decimal" value={points} onChange={(e) => { setPoints(e.target.value); setIssues([]); }}
          placeholder={fmtNum(sub.effective_points ?? sub.raw_points)} aria-invalid={!!pointsIssue} className={`${inputCls} max-w-[10rem]`} />
        {pointsIssue && <p role="alert" className="mt-1 text-xs text-red-700">{t(`gradebook.override.issues.${pointsIssue}`, { max })}</p>}
      </div>
      <div>
        <label htmlFor={rid} className="mb-1 block text-sm font-medium text-slate-700">{t("gradebook.reason.required")}</label>
        <textarea id={rid} value={reason} rows={2} maxLength={REASON_MAX} onChange={(e) => { setReason(e.target.value); setIssues([]); }}
          aria-invalid={!!reasonIssue} className={inputCls} />
        {reasonIssue && <p role="alert" className="mt-1 text-xs text-red-700">{t(`gradebook.override.issues.${reasonIssue}`)}</p>}
      </div>
      <button type="submit" disabled={busy} className={btnPrimary}>{busy ? t("lms.common.loading") : t("gradebook.override.save")}</button>
    </form>
  );
}
