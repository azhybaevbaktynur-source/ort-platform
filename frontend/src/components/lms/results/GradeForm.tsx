"use client";

import React, { useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { inputCls, labelCls } from "@/components/lms/content/ui";
import { btnPrimary } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { scoreAttemptItem, type AttemptStaffOut, type StaffReviewItem } from "@/lib/lms/staffAttempts";
import { fmtPoints } from "@/components/lms/assessments/format";

/** Manual score + feedback for one item; points must be within 0..max (the server checks it too). */
export function GradeForm({
  courseId,
  attemptId,
  item,
  max,
  disabled,
  onSaved,
}: {
  courseId: string;
  attemptId: string;
  item: StaffReviewItem;
  max: number | null;
  disabled?: boolean;
  onSaved: (a: AttemptStaffOut) => void;
}) {
  const { t } = useTranslation();
  const initial = item.manual_score ?? (item.correctness === "pending" ? "" : item.score ?? "");
  const [points, setPoints] = useState<string>(initial === "" ? "" : fmtPoints(initial));
  const [feedback, setFeedback] = useState(item.feedback ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  const n = Number(points.replace(",", "."));
  const valid = points.trim() !== "" && Number.isFinite(n) && n >= 0 && (max === null || n <= max);

  async function save(ev: React.FormEvent) {
    ev.preventDefault();
    if (!valid || saving) return;
    setSaving(true);
    setSaved(false);
    try {
      const out = await scoreAttemptItem(courseId, attemptId, item.position, { points: n, feedback: feedback.trim() ? feedback.trim() : null });
      setError(null);
      setSaved(true);
      onSaved(out);
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-3 rounded-xl border border-indigo-200 bg-indigo-50/50 p-4">
      <h4 className="text-sm font-semibold text-slate-900">{t("grading.manualScore")}</h4>
      {item.auto_score !== null && item.auto_score !== undefined && (
        <p className="text-xs text-slate-500">{t("grading.autoScore", { score: fmtPoints(item.auto_score) })}</p>
      )}
      <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
        <div>
          <label htmlFor={`pts-${item.position}`} className={labelCls}>
            {max !== null ? t("grading.pointsMax", { max: fmtPoints(max) }) : t("grading.points")}
          </label>
          <input id={`pts-${item.position}`} type="text" inputMode="decimal" value={points} disabled={disabled || saving}
            onChange={(e) => { setPoints(e.target.value); setSaved(false); }} className={inputCls}
            aria-invalid={points.trim() !== "" && !valid} />
          {points.trim() !== "" && !valid && <p className="mt-1 text-xs text-red-700">{t("grading.pointsInvalid")}</p>}
        </div>
        <div>
          <label htmlFor={`fb-${item.position}`} className={labelCls}>{t("grading.feedback")}</label>
          <textarea id={`fb-${item.position}`} rows={3} maxLength={5000} value={feedback} disabled={disabled || saving}
            onChange={(e) => { setFeedback(e.target.value); setSaved(false); }} className={inputCls} />
        </div>
      </div>
      <ErrorMessage error={error} />
      <div className="flex items-center gap-3">
        <button type="submit" disabled={disabled || saving || !valid} className={btnPrimary}>{saving ? t("grading.saving") : t("grading.save")}</button>
        {saved && <span role="status" className="text-sm text-emerald-700">{t("grading.saved")}</span>}
      </div>
    </form>
  );
}
