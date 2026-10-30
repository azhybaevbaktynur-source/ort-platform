"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { deleteAssessment, listAssessments, restoreAssessment } from "@/lib/lms/assessments";
import type { AssessmentStaffSummaryOut } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { withFrom } from "@/lib/lms/nav"; // Phase 8c S2
import { useCourse } from "@/components/lms/CourseContext";
import { Pager } from "@/components/lms/Pager";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { btnSmall } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { AssessmentStatusBadge, useListCount } from "@/components/lms/course/StaffCourseUi";
import { Badge, Button, ConfirmDialog, EmptyState, LoadingState, PageHeader } from "@/components/ui";
import { AssessmentError } from "./AssessmentError";
import { CreateAssessmentDialog } from "./CreateAssessmentDialog";
import { IssueList } from "./IssueList";
import { fmtDateTime, fmtPoints } from "./format";
import { usePublishFlow } from "./usePublishFlow";
import { KeyRound } from "lucide-react"; // Phase 7a S5

/**
 * Staff assessment list. Phase 6b S5c: design-system PageHeader (one primary: "New assessment"), status Badges,
 * EmptyState with its own button (UX T24), action row under the text on phones (T6), unpublish through a
 * confirmation that names the assessment and its attempts (T6). `?new=1` opens the create dialog (course home link).
 */
// Phase 8c S2 (PHASE_8C_DESIGN §3.7, P8C-7): the Tests list is gone; this list lives on the ORT teacher Course page
// (`embedded`: the course title is the page `<h1>`, so the list title is an `<h2>`; `?new=1` is cleared on the page
// itself instead of the old `/assessments` route, which is now a redirect stub). The list content is unchanged.
export function StaffAssessmentList({ embedded = false }: { embedded?: boolean } = {}) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const router = useRouter();
  const search = useSearchParams();
  const pathname = usePathname() || "";
  const base = `/${lang}/courses/${course.id}/assessments`;
  // Phase 8c S2: from the Course page the builder's Back leads to it (`from`, §5.3)
  const editHref = (id: string) => (embedded ? withFrom(`${base}/${id}/edit`, `/${lang}/courses/${course.id}`) : `${base}/${id}/edit`);
  const [trash, setTrash] = useState(false);
  const [items, setItems] = useState<AssessmentStaffSummaryOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);
  const [toDelete, setToDelete] = useState<AssessmentStaffSummaryOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const countText = useListCount();

  useEffect(() => {
    if (search.get("new") === "1" && canEdit) {
      setCreating(true);
      router.replace(embedded ? pathname : base);
    }
  }, [search, canEdit, router, base, embedded, pathname]);

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

  const titleOf = (a: AssessmentStaffSummaryOut) => pickLocalized(a.title, lang, course.default_language) || t("assessments.untitled");
  const create = canEdit && !trash ? <Button onClick={() => setCreating(true)}>{t("assessments.list.create")}</Button> : undefined;

  return (
    <div className="space-y-4">
      {embedded ? (
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold leading-7 text-slate-900">{t("assessments.list.title")}</h2>
            {!loading && !error && items.length > 0 && <p className="mt-1 text-sm leading-6 text-slate-600">{countText(items.length, !!cursor)}</p>}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <Button variant="secondary" onClick={() => setTrash((s) => !s)}>{trash ? t("assessments.list.hideTrash") : t("assessments.list.showTrash")}</Button>
            {canEdit && <Button onClick={() => setCreating(true)}>{t("assessments.list.create")}</Button>}
          </div>
        </div>
      ) : (
        <PageHeader title={t("assessments.list.title")} className="mb-2"
          description={!loading && !error && items.length > 0 ? countText(items.length, !!cursor) : undefined}
          secondaryActions={<Button variant="secondary" onClick={() => setTrash((s) => !s)}>{trash ? t("assessments.list.hideTrash") : t("assessments.list.showTrash")}</Button>}
          primaryAction={canEdit ? <Button onClick={() => setCreating(true)}>{t("assessments.list.create")}</Button> : undefined} />
      )}
      <AssessmentError error={error} onRetry={error ? () => load() : undefined} />
      {!toDelete && <AssessmentError error={actionError} />}
      <AssessmentError error={flow.error} />
      <IssueList issues={flow.issues} kind="error" />
      {loading && items.length === 0 && !error && <LoadingState rows={3} />}
      {!loading && !error && items.length === 0 && (
        <EmptyState title={trash ? t("assessments.list.emptyTrash") : t("assessments.list.empty")}
          description={trash ? undefined : t("teaching.assessmentsEmptyHint")} action={create} />
      )}
      <ul className="space-y-3">
        {items.map((a) => {
          const title = titleOf(a);
          return (
            <li key={a.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1 basis-full sm:basis-0">
                  <div className="flex flex-wrap items-center gap-2">
                    {a.deleted_at ? <h2 className="break-words font-semibold text-slate-900">{title}</h2>
                      : <Link href={`${base}/${a.id}`} className="break-words font-semibold text-slate-900 hover:text-brand-700">{title}</Link>}
                    <AssessmentStatusBadge status={a.status} />
                    {a.current_version_no !== null && <Badge tone="neutral">{t("assessments.list.version", { n: a.current_version_no })}</Badge>}
                    {a.has_access_code && <Badge tone="info" icon={<KeyRound aria-hidden="true" />}>{t("accommodations.accessCode.badge")}</Badge> /* Phase 7a S5 */}
                    {a.has_unpublished_changes && a.status === "published" && (
                      <Badge tone="warning">{t("assessments.list.unpublishedChanges")}</Badge>
                    )}
                  </div>
                  <p className="mt-1 text-sm text-slate-600">
                    {t("assessments.list.counts", { items: a.item_count, points: fmtPoints(a.points_possible) })}
                    {" · "}{a.languages.map((l) => l.toUpperCase()).join(", ")}
                    {" · "}{t("assessments.list.attempts", { inProgress: a.attempt_counts.in_progress, submitted: a.attempt_counts.submitted })}
                  </p>
                  {(a.available_from || a.available_until) && (
                    <p className="text-sm text-slate-600">
                      {a.available_from ? t("assessments.list.from", { date: fmtDateTime(a.available_from) }) : ""}
                      {a.available_from && a.available_until ? " · " : ""}
                      {a.available_until ? t("assessments.list.until", { date: fmtDateTime(a.available_until) }) : ""}
                    </p>
                  )}
                </div>
                {canEdit && (
                  <div className="flex w-full flex-wrap gap-2 sm:w-auto">
                    {a.deleted_at ? (
                      <button type="button" className={btnSmall} onClick={() => void restore(a)}>{t("assessments.list.restore")}</button>
                    ) : (
                      <>
                        <Link href={editHref(a.id)} className={btnSmall}>{t("assessments.list.edit")}</Link>
                        {a.status === "published" ? (
                          <button type="button" className={btnSmall} disabled={flow.busyId === a.id}
                            onClick={() => flow.requestUnpublish(a.id, title, a.attempt_counts)}>{t("assessments.publish.unpublish")}</button>
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
        onCreated={(a) => { setCreating(false); router.push(editHref(a.id)); }} onCancel={() => setCreating(false)} />
      <ConfirmDialog open={!!toDelete} tone="danger" busy={busy} title={t("assessments.list.deleteTitle")}
        object={toDelete ? titleOf(toDelete) : undefined} effect={t("assessments.list.deleteBody")}
        confirmLabel={t("assessments.list.delete")} onConfirm={() => void remove()} onCancel={() => setToDelete(null)}
        error={actionError ? <AssessmentError error={actionError} /> : undefined} />
      {flow.dialog}
    </div>
  );
}
