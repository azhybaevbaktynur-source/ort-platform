"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { deleteAssessment, listAssessments, restoreAssessment } from "@/lib/lms/assessments";
import type { AssessmentStaffSummaryOut } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { useCourse } from "@/components/lms/CourseContext";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { Pager } from "@/components/lms/Pager";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { btnPrimary, btnSecondary, btnSmall } from "@/components/lms/content/ui";
import { AssessmentError } from "./AssessmentError";
import { CreateAssessmentDialog } from "./CreateAssessmentDialog";
import { IssueList } from "./IssueList";
import { fmtDateTime, fmtPoints } from "./format";
import { usePublishFlow } from "./usePublishFlow";

export function StaffAssessmentList() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const router = useRouter();
  const base = `/${lang}/courses/${course.id}/assessments`;
  const [trash, setTrash] = useState(false);
  const [items, setItems] = useState<AssessmentStaffSummaryOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);
  const [toDelete, setToDelete] = useState<AssessmentStaffSummaryOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listAssessments(course.id, { deleted: trash, cursor: next, limit: 50 });
      const rows = page.items as AssessmentStaffSummaryOut[];
      setItems((p) => (next ? [...p, ...rows] : rows));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id, trash]);
  useEffect(() => { void load(); }, [load]);

  const flow = usePublishFlow(course.id, () => load());

  const remove = async () => {
    if (!toDelete) return;
    setBusy(true);
    setActionError(null);
    try {
      await deleteAssessment(course.id, toDelete.id);
      setToDelete(null);
      await load();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };
  const restore = async (a: AssessmentStaffSummaryOut) => {
    setActionError(null);
    try {
      await restoreAssessment(course.id, a.id);
      await load();
    } catch (e) {
      setActionError(e);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold text-slate-900">{t("assessments.list.title")}</h2>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={btnSecondary} onClick={() => setTrash((s) => !s)}>{trash ? t("assessments.list.hideTrash") : t("assessments.list.showTrash")}</button>
          {canEdit && <button type="button" className={btnPrimary} onClick={() => setCreating(true)}>{t("assessments.list.create")}</button>}
        </div>
      </div>
      <AssessmentError error={error} onRetry={error ? () => load() : undefined} />
      {!toDelete && <AssessmentError error={actionError} />}
      <AssessmentError error={flow.error} />
      <IssueList issues={flow.issues} kind="error" />
      {loading && items.length === 0 && !error && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
      {!loading && !error && items.length === 0 && <p className="text-sm text-slate-500">{trash ? t("assessments.list.emptyTrash") : t("assessments.list.empty")}</p>}
      <ul className="space-y-3">
        {items.map((a) => {
          const title = pickLocalized(a.title, lang, course.default_language) || t("assessments.untitled");
          return (
            <li key={a.id} className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    {a.deleted_at ? <h3 className="font-semibold text-slate-900">{title}</h3>
                      : <Link href={`${base}/${a.id}`} className="font-semibold text-slate-900 hover:text-brand-700">{title}</Link>}
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${a.status === "published" ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>
                      {t(`assessments.status.${a.status}`)}
                    </span>
                    {a.current_version_no !== null && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{t("assessments.list.version", { n: a.current_version_no })}</span>}
                    {a.has_unpublished_changes && a.status === "published" && (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">{t("assessments.list.unpublishedChanges")}</span>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {t("assessments.list.counts", { items: a.item_count, points: fmtPoints(a.points_possible) })}
                    {" · "}{a.languages.map((l) => l.toUpperCase()).join(", ")}
                    {" · "}{t("assessments.list.attempts", { inProgress: a.attempt_counts.in_progress, submitted: a.attempt_counts.submitted })}
                  </p>
                  {(a.available_from || a.available_until) && (
                    <p className="text-xs text-slate-400">
                      {a.available_from ? t("assessments.list.from", { date: fmtDateTime(a.available_from) }) : ""}
                      {a.available_from && a.available_until ? " · " : ""}
                      {a.available_until ? t("assessments.list.until", { date: fmtDateTime(a.available_until) }) : ""}
                    </p>
                  )}
                </div>
                {canEdit && (
                  <div className="flex flex-wrap gap-2">
                    {a.deleted_at ? (
                      <button type="button" className={btnSmall} onClick={() => void restore(a)}>{t("assessments.list.restore")}</button>
                    ) : (
                      <>
                        <Link href={`${base}/${a.id}/edit`} className={btnSmall}>{t("assessments.list.edit")}</Link>
                        {a.status === "published" ? (
                          <button type="button" className={btnSmall} disabled={flow.busyId === a.id} onClick={() => void flow.unpublish(a.id)}>{t("assessments.publish.unpublish")}</button>
                        ) : (
                          <button type="button" className={btnSmall} disabled={flow.busyId === a.id} onClick={() => void flow.publish(a.id)}>{t("assessments.publish.publish")}</button>
                        )}
                        <button type="button" className={btnSmall} onClick={() => { setActionError(null); setToDelete(a); }}>{t("assessments.list.delete")}</button>
                      </>
                    )}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
      <CreateAssessmentDialog open={creating} courseId={course.id} courseLanguages={course.languages} defaultLanguage={course.default_language}
        onCreated={(a) => { setCreating(false); router.push(`${base}/${a.id}/edit`); }} onCancel={() => setCreating(false)} />
      <ConfirmDialog open={!!toDelete} danger busy={busy} title={t("assessments.list.deleteTitle")} body={t("assessments.list.deleteBody")}
        confirmLabel={t("assessments.list.delete")} onConfirm={() => void remove()} onCancel={() => setToDelete(null)}>
        <AssessmentError error={actionError} className="mt-3" />
      </ConfirmDialog>
      {flow.dialog}
    </div>
  );
}
