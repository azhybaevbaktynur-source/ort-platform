"use client";

// Phase 8a S4b: Files tab (design 8.1). Folders are path strings, shown as collapsible groups. Students download
// published files; staff upload (PDF, 10 MB), rename / move / publish and delete. A locked module answers the download
// with 423, which becomes the friendly locked state.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Download, FileText, FolderOpen, Upload } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { deleteCourseFile, downloadCourseFile, listCourseFiles } from "@/lib/lms/courseFiles";
import type { CourseFileStaffOut, CourseFileStudentOut, CourseFilesQuotaOut } from "@/lib/lms/pagesTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { ContentError, LockedState, isModuleLocked } from "@/components/lms/pages/ApiError";
import { Badge, Button, ConfirmDialog, EmptyState, LoadingState, MenuButton, PageHeader, Pagination } from "@/components/ui";
import { EditFileDialog } from "./EditFileDialog";
import { UploadFileDialog } from "./UploadFileDialog";
import { useFmtBytes } from "./useFmtBytes";

type Row = CourseFileStaffOut | CourseFileStudentOut;
const isStaffRow = (r: Row): r is CourseFileStaffOut => "published" in r;

export function CourseFilesView() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const isStaff = course.my_enrollment.role === "teacher" || course.my_enrollment.role === "assistant";
  const fmtBytes = useFmtBytes();
  const [items, setItems] = useState<Row[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [quota, setQuota] = useState<CourseFilesQuotaOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [upload, setUpload] = useState(false);
  const [edit, setEdit] = useState<CourseFileStaffOut | null>(null);
  const [confirm, setConfirm] = useState<CourseFileStaffOut | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (next?: string | null) => {
    if (next) setMore(true); else setLoading(true);
    setError(null);
    try {
      const page = await listCourseFiles(course.id, { cursor: next, limit: 100 });
      setItems((p) => (next ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
      if (page.quota) setQuota(page.quota);
    } catch (e) { setError(e); } finally { setLoading(false); setMore(false); }
  }, [course.id]);
  useEffect(() => { void load(); }, [load]);

  const groups = useMemo(() => {
    const m = new Map<string, Row[]>();
    for (const r of items) m.set(r.folder, [...(m.get(r.folder) ?? []), r]);
    return [...m.entries()].sort(([a], [b]) => (a === "" ? -1 : b === "" ? 1 : a.localeCompare(b)));
  }, [items]);
  const folders = useMemo(() => [...new Set(items.map((r) => r.folder).filter(Boolean))].sort(), [items]);

  const download = async (r: Row) => {
    setDownloading(r.id); setActionError(null);
    try { await downloadCourseFile(course.id, r.id, isStaffRow(r) ? r.filename : null); }
    catch (e) { setActionError(e); } finally { setDownloading(null); }
  };
  const doDelete = async () => {
    if (!confirm) return;
    setBusy(true); setActionError(null);
    try { await deleteCourseFile(course.id, confirm.id); setConfirm(null); await load(); }
    catch (e) { setConfirm(null); setActionError(e); } finally { setBusy(false); }
  };

  const pct = quota && quota.max > 0 ? Math.min(100, Math.round((quota.used / quota.max) * 100)) : 0;

  return (
    <div>
      <PageHeader
        title={t("courseFiles.title")}
        description={t(isStaff ? "courseFiles.descriptionStaff" : "courseFiles.descriptionStudent")}
        primaryAction={canEdit ? <Button leftIcon={<Upload className="h-4 w-4" aria-hidden="true" />} onClick={() => setUpload(true)}>{t("courseFiles.upload")}</Button> : undefined}
      />
      {isStaff && quota && (
        <div className="mb-5 rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
            <span className="font-medium text-slate-800">{t("courseFiles.quota")}</span>
            <span className="text-slate-600">{t("courseFiles.quotaUsed", { used: fmtBytes(quota.used), max: fmtBytes(quota.max) })}</span>
          </div>
          <div role="progressbar" aria-label={t("courseFiles.quota")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200">
            <div className={`h-full ${pct >= 90 ? "bg-danger-600" : "bg-brand-600"}`} style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}
      {isModuleLocked(actionError) ? (
        <div className="mb-5"><LockedState error={actionError} courseId={course.id} compact /></div>
      ) : (
        <ContentError error={actionError} className="mb-4" />
      )}
      {loading ? <LoadingState /> : error ? <ContentError error={error} onRetry={() => void load()} /> : items.length === 0 ? (
        <EmptyState
          title={t("courseFiles.empty")}
          description={isStaff ? t("courseFiles.emptyHintStaff") : t("courseFiles.emptyHintStudent")}
          icon={<FileText className="h-6 w-6" aria-hidden="true" />}
          action={canEdit ? <Button onClick={() => setUpload(true)}>{t("courseFiles.upload")}</Button> : undefined}
        />
      ) : (
        <div className="space-y-4">
          {groups.map(([folder, rows]) => (
            <details key={folder} open className="rounded-xl border border-slate-200 bg-white">
              <summary className="flex min-h-11 cursor-pointer items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-900">
                <FolderOpen className="h-4 w-4 shrink-0 text-slate-600" aria-hidden="true" />
                <span className="min-w-0 break-words">{folder || t("courseFiles.rootFolder")}</span>
                <span className="ml-auto text-xs font-normal text-slate-600">{t("courseFiles.filesCount", { count: rows.length })}</span>
              </summary>
              <ul className="divide-y divide-slate-100 border-t border-slate-100">
                {rows.map((r) => (
                  <li key={r.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
                    <div className="min-w-0 flex-1">
                      <p className="break-words font-medium text-slate-900">{r.title}</p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-600">
                        <span>{fmtBytes(r.bytes)}</span>
                        <span aria-hidden="true">·</span>
                        <span>{fmtShortDateTime(r.created_at, lang)}</span>
                        {isStaffRow(r) && !r.published && <Badge tone="neutral">{t("courseFiles.draft")}</Badge>}
                        {isStaffRow(r) && r.used_in_modules > 0 && <span>{t("courseFiles.usedInModules", { count: r.used_in_modules })}</span>}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button variant="secondary" size="sm" loading={downloading === r.id} leftIcon={<Download className="h-4 w-4" aria-hidden="true" />} onClick={() => void download(r)}>
                        {t("courseFiles.download")}<span className="sr-only">: {r.title}</span>
                      </Button>
                      {canEdit && isStaffRow(r) && (
                        <MenuButton variant="secondary" size="sm"
                          label={<>{t("courseFiles.actions")}<span className="sr-only">: {r.title}</span></>}
                          items={[{ id: "edit", label: t("courseFiles.edit") }, { id: "delete", label: t("courseFiles.delete") }]}
                          onSelect={(id) => (id === "edit" ? setEdit(r) : setConfirm(r))} />
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </div>
      )}
      <Pagination nextCursor={cursor} onLoadMore={() => void load(cursor)} loading={more} />

      {canEdit && (
        <>
          <UploadFileDialog open={upload} courseId={course.id} folders={folders} onClose={() => setUpload(false)} onDone={() => { setUpload(false); void load(); }} />
          <EditFileDialog file={edit} courseId={course.id} folders={folders} onClose={() => setEdit(null)} onDone={() => { setEdit(null); void load(); }} />
          <ConfirmDialog
            open={!!confirm} title={t("courseFiles.deleteTitle")} object={confirm?.title}
            effect={confirm && confirm.used_in_modules > 0 ? t("courseFiles.deleteEffectUsed", { count: confirm.used_in_modules }) : t("courseFiles.deleteEffect")}
            confirmLabel={t("courseFiles.delete")} tone="danger" busy={busy} onConfirm={() => void doDelete()} onCancel={() => setConfirm(null)}
          />
        </>
      )}
    </div>
  );
}
