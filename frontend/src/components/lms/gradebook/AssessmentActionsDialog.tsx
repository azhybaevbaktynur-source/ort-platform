"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import type { GbAssignmentOut } from "@/lib/lms/gradingTypes";
// Phase 7a S5: the column is an assignment; release / unrelease / regrade use the assignment routes.
import { regradeAssignmentGrades, releaseGrades, unreleaseGrades } from "@/lib/lms/grading";
import { Modal } from "@/components/lms/assessments/Modal";
import { SchemeError } from "@/components/lms/grading/schemes/SchemeError";
import { ScaleText } from "@/components/lms/grading/schemes/SchemeBadges";
import { btnPrimary, btnSecondary } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { fmtDateTime } from "@/components/lms/assessments/format";
import { runRegrade, type RegradeEnd, type RegradeProgress } from "./gradebookModel";
import { useWarningText } from "./warnings";

type Notice = { kind: "ok" | "warn"; text: string } | null;

/** Per-assessment grade actions: release all, hide all, regrade (looped until nothing is pending). */
export function AssessmentActionsDialog({
  open, courseId, assessment, title, defaultLanguage, canManage, onClose, onChanged,
}: {
  open: boolean;
  courseId: string;
  assessment: GbAssignmentOut | null;
  title: string;
  defaultLanguage: Lang;
  canManage: boolean;
  onClose: () => void;
  /** grades changed server-side: the grid should reload */
  onChanged: () => void;
}) {
  const { lang, t } = useTranslation();
  const warningText = useWarningText();
  const [busy, setBusy] = useState<"" | "release" | "unrelease" | "regrade">("");
  const [confirmUnrelease, setConfirmUnrelease] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [progress, setProgress] = useState<RegradeProgress | null>(null);
  const stopRef = useRef(false);
  const changedRef = useRef(false);

  useEffect(() => {
    if (open) { setError(null); setNotice(null); setProgress(null); setConfirmUnrelease(false); changedRef.current = false; }
  }, [open, assessment?.id]);

  if (!assessment) return null;
  const a = assessment;

  function close() {
    if (busy) return;
    if (changedRef.current) onChanged();
    onClose();
  }

  async function release() {
    setBusy("release"); setError(null); setNotice(null);
    try {
      const r = await releaseGrades(courseId, a.id);
      changedRef.current = true;
      setNotice({ kind: "ok", text: t("gradebook.actions.releasedN", { n: r.released }) });
    } catch (e) { setError(e); } finally { setBusy(""); }
  }

  async function unrelease() {
    setBusy("unrelease"); setError(null); setNotice(null);
    try {
      const r = await unreleaseGrades(courseId, a.id);
      changedRef.current = true;
      setConfirmUnrelease(false);
      setNotice({ kind: "ok", text: t("gradebook.actions.unreleasedN", { n: r.unreleased }) });
    } catch (e) { setError(e); } finally { setBusy(""); }
  }

  async function regrade() {
    setBusy("regrade"); setError(null); setNotice(null); setProgress(null);
    stopRef.current = false;
    let end: RegradeEnd | null = null;
    let last: RegradeProgress | null = null;
    try {
      const r = await runRegrade(() => regradeAssignmentGrades(courseId, a.id), (p) => { last = p; setProgress(p); }, () => stopRef.current);
      end = r.end;
      last = r.progress;
    } catch (e) {
      setError(e);
    } finally {
      setBusy("");
    }
    const p = last as RegradeProgress | null;
    if (p && p.regraded > 0) changedRef.current = true;
    if (!end || !p) return;
    if (end === "done") setNotice({ kind: "ok", text: t("gradebook.actions.regradeDone", { n: p.regraded }) });
    else if (end === "stalled") setNotice({ kind: "warn", text: t("gradebook.actions.regradeStalled", { pending: p.pending }) });
    else setNotice({ kind: "warn", text: t("gradebook.actions.regradePaused", { pending: p.pending }) });
  }

  // Phase 7a S5: quiz columns open the attempts list, other kinds the grading screen
  const attemptsHref = a.kind === "quiz" && a.assessment_id
    ? `/${lang}/courses/${courseId}/assessments/${a.assessment_id}/attempts`
    : `/${lang}/courses/${courseId}/assignments/${a.id}/grade`;
  const scheme = a.scheme;
  // auto release: the next scoring or regrade would release again, so the server refuses to hide (409)
  const autoRelease = a.grade_release === "auto";
  return (
    <Modal open={open} title={title || t("gradebook.untitled")} onClose={close} busy={!!busy}>
      <div className="space-y-4 text-sm">
        <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-slate-700">
          <dt className="text-slate-500">{t("gradebook.actions.submissions")}</dt>
          <dd>{t("gradebook.actions.releasedOf", { released: a.released_count, total: a.submission_count })}</dd>
          <dt className="text-slate-500">{t("gradebook.actions.releaseMode")}</dt>
          <dd>{t(`gradebook.releaseMode.${a.grade_release}`)}</dd>
          {a.score_policy && (<><dt className="text-slate-500">{t("gradebook.actions.keptRule")}</dt>
          <dd>{t(`assessments.scorePolicy.${a.score_policy}`)}</dd></>)}
          <dt className="text-slate-500">{t("gradebook.actions.scheme")}</dt>
          <dd className="min-w-0 break-words">
            {scheme ? (
              <>
                {pickLocalized(scheme.title, lang, defaultLanguage)}{" · "}{t("schemes.library.version", { n: scheme.version_no })}
                {" "}<span className="text-slate-500"><ScaleText min={scheme.scale_min} max={scheme.scale_max} /></span>
              </>
            ) : t("gradebook.actions.noScheme")}
          </dd>
          {a.due_at && (<><dt className="text-slate-500">{t("gradebook.actions.due")}</dt><dd>{fmtDateTime(a.due_at)}</dd></>)}
          {a.omit_from_total && (<><dt className="text-slate-500">{t("gradebook.actions.total")}</dt><dd>{t("gradebook.header.omitted")}</dd></>)}
        </dl>

        {a.warnings.length > 0 && (
          <ul className="list-disc space-y-1 rounded-xl border border-amber-200 bg-amber-50 py-2 pl-8 pr-3 text-amber-900">
            {a.warnings.map((w) => <li key={w}>{warningText(w)}</li>)}
          </ul>
        )}

        {a.stale_count > 0 && (
          <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">{t("gradebook.actions.staleN", { n: a.stale_count })}</p>
        )}

        {canManage && (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={!!busy} onClick={() => void release()} className={btnPrimary}>
                {busy === "release" ? t("lms.common.loading") : t("gradebook.actions.releaseAll")}
              </button>
              {!autoRelease && (
                <button type="button" disabled={!!busy} onClick={() => setConfirmUnrelease(true)} className={btnSecondary}>
                  {t("gradebook.actions.unreleaseAll")}
                </button>
              )}
              <button type="button" disabled={!!busy} onClick={() => void regrade()} className={btnSecondary}>
                {busy === "regrade" ? t("gradebook.actions.regrading") : t("gradebook.actions.regrade")}
              </button>
            </div>
            <p className="text-xs text-slate-500">{t("gradebook.actions.releaseHint")}</p>
            {autoRelease && <p className="text-xs text-slate-500">{t("gradebook.actions.unreleaseAutoHint")}</p>}
            <p className="text-xs text-slate-500">{t("gradebook.actions.regradeHint")}</p>

            {confirmUnrelease && !autoRelease && (
              <div role="alertdialog" aria-label={t("gradebook.actions.unreleaseAll")} className="rounded-xl border border-red-200 bg-red-50 p-3">
                <p className="text-red-900">{t("gradebook.actions.unreleaseConfirm")}</p>
                <div className="mt-2 flex gap-2">
                  <button type="button" disabled={!!busy} onClick={() => void unrelease()}
                    className="rounded-xl bg-red-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50">
                    {busy === "unrelease" ? t("lms.common.loading") : t("gradebook.actions.unreleaseAll")}
                  </button>
                  <button type="button" disabled={!!busy} onClick={() => setConfirmUnrelease(false)} className={btnSecondary}>
                    {t("lms.common.cancel")}
                  </button>
                </div>
              </div>
            )}

            {busy === "regrade" && (
              <div role="status" className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                <span>{progress
                  ? t("gradebook.actions.regradeProgress", { done: progress.regraded, pending: progress.pending })
                  : t("gradebook.actions.regrading")}</span>
                <button type="button" onClick={() => { stopRef.current = true; }} className="text-sm font-semibold text-brand-700 underline">
                  {t("gradebook.actions.stop")}
                </button>
              </div>
            )}
          </div>
        )}

        {notice && (
          <p role="status" className={`rounded-xl px-3 py-2 ${notice.kind === "ok" ? "border border-emerald-200 bg-emerald-50 text-emerald-900" : "border border-amber-200 bg-amber-50 text-amber-900"}`}>
            {notice.text}
          </p>
        )}
        <SchemeError error={error} />

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
          <Link href={attemptsHref} className="font-medium text-brand-700 hover:underline">
            {a.kind === "quiz" ? t("gradebook.actions.openAttempts") : t("assignments.gradebook.openGrading")}
          </Link>
          <button type="button" disabled={!!busy} onClick={close} className={btnSecondary}>{t("gradebook.close")}</button>
        </div>
      </div>
    </Modal>
  );
}
