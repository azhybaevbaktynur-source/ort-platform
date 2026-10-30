"use client";

// Phase 8a S4b: Pages tab for staff (table: title, language, status, used in N modules) and a plain list for a student
// who opens /pages directly (students normally reach pages from modules or the course home).
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileText, Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { deletePage, listPages, restorePage } from "@/lib/lms/pages";
import type { PageSummaryStaffOut, PageSummaryStudentOut } from "@/lib/lms/pagesTypes";
import { withFrom } from "@/lib/lms/nav";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { Badge, Button, Checkbox, ConfirmDialog, EmptyState, LinkButton, LoadingState, MenuButton, PageHeader, Pagination, Table, type TableColumn } from "@/components/ui";
import { ContentError } from "./ApiError";

export function PageList() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const router = useRouter();
  const isStaff = course.my_enrollment.role === "teacher" || course.my_enrollment.role === "assistant";
  const base = `/${lang}/courses/${course.id}`;
  const [trash, setTrash] = useState(false);
  const [items, setItems] = useState<Array<PageSummaryStaffOut | PageSummaryStudentOut>>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [confirm, setConfirm] = useState<PageSummaryStaffOut | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (next?: string | null) => {
    if (next) setMore(true); else setLoading(true);
    setError(null);
    try {
      const page = await listPages(course.id, { cursor: next, limit: 50, deleted: isStaff ? trash : undefined });
      setItems((p) => (next ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) { setError(e); } finally { setLoading(false); setMore(false); }
  }, [course.id, trash, isStaff]);
  useEffect(() => { void load(); }, [load]);

  const doDelete = async () => {
    if (!confirm) return;
    setBusy(true); setActionError(null);
    try { await deletePage(course.id, confirm.id); setConfirm(null); await load(); }
    catch (e) { setConfirm(null); setActionError(e); } finally { setBusy(false); }
  };
  const doRestore = async (p: PageSummaryStaffOut) => {
    setActionError(null);
    try { await restorePage(course.id, p.id); await load(); } catch (e) { setActionError(e); }
  };

  const newButton = canEdit ? (
    <LinkButton href={withFrom(`${base}/pages/new`, `${base}/pages`)} leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}>{t("pages.new")}</LinkButton>
  ) : undefined;

  if (!isStaff) {
    return (
      <div>
        <PageHeader title={t("pages.title")} />
        {loading ? <LoadingState /> : error ? <ContentError error={error} onRetry={() => void load()} /> : items.length === 0 ? (
          <EmptyState title={t("pages.studentEmpty")} icon={<FileText className="h-6 w-6" aria-hidden="true" />} />
        ) : (
          <ul className="space-y-2">
            {items.map((p) => (
              <li key={p.id}>
                <Link href={`${base}/pages/${p.id}`} className="flex min-h-11 items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 hover:bg-slate-50">
                  <span className="min-w-0 break-words font-medium text-slate-900">{p.title}</span>
                  <Badge tone="info">{t(`pages.lang.${p.language}`)}</Badge>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <Pagination nextCursor={cursor} onLoadMore={() => void load(cursor)} loading={more} />
      </div>
    );
  }

  const columns: TableColumn<PageSummaryStaffOut>[] = [
    {
      key: "title", header: t("pages.col.title"), label: t("pages.col.title"), primary: true,
      cell: (p) => <Link href={withFrom(`${base}/pages/${p.id}`, `${base}/pages`)} className="font-medium text-brand-700 hover:underline">{p.title}</Link>,
    },
    { key: "language", header: t("pages.col.language"), label: t("pages.col.language"), cell: (p) => t(`pages.lang.${p.language}`) },
    {
      key: "status", header: t("pages.col.status"), label: t("pages.col.status"),
      cell: (p) => <Badge tone={p.published ? "success" : "neutral"}>{t(p.published ? "pages.published" : "pages.draft")}</Badge>,
    },
    { key: "modules", header: t("pages.col.modules"), label: t("pages.col.modules"), cell: (p) => t("pages.usedInModules", { count: p.used_in_modules }) },
    { key: "updated", header: t("pages.col.updated"), label: t("pages.col.updated"), cell: (p) => fmtShortDateTime(p.updated_at, lang) },
    ...(canEdit ? [{
      key: "actions", header: <span className="sr-only">{t("pages.col.actions")}</span>, label: t("pages.col.actions"), align: "right" as const, actions: true,
      cell: (p: PageSummaryStaffOut) => trash ? (
        <Button variant="secondary" size="sm" onClick={() => void doRestore(p)}>{t("pages.restore")}</Button>
      ) : (
        <MenuButton variant="secondary" size="sm"
          label={<>{t("pages.col.actions")}<span className="sr-only">: {p.title}</span></>}
          items={[{ id: "edit", label: t("pages.edit") }, { id: "view", label: t("pages.view.open") }, { id: "delete", label: t("pages.delete") }]}
          onSelect={(id) => {
            if (id === "delete") setConfirm(p);
            else router.push(withFrom(`${base}/pages/${p.id}?tab=${id === "edit" ? "edit" : "preview"}`, `${base}/pages`)); // Phase 8c S3
          }} />
      ),
    }] : []),
  ];

  return (
    <div>
      <PageHeader title={t("pages.title")} description={t("pages.description")} primaryAction={newButton} />
      {/* 8a UX (minor 10): a filter, not an action: a checkbox under the header instead of a second button */}
      <Checkbox label={t("pages.showTrash")} checked={trash} onChange={(e) => setTrash(e.target.checked)} containerClassName="mb-2" />
      <ContentError error={actionError} className="mb-4" />
      <Table<PageSummaryStaffOut>
        caption={t("pages.title")}
        columns={columns}
        rows={items as PageSummaryStaffOut[]}
        rowKey={(p) => p.id}
        loading={loading}
        error={error ? <ContentError error={error} onRetry={() => void load()} /> : undefined}
        empty={<EmptyState variant="plain" title={t(trash ? "pages.trashEmpty" : "pages.empty")} description={trash ? undefined : t("pages.emptyHint")} action={trash ? undefined : newButton} />}
        pagination={{ nextCursor: cursor, onLoadMore: () => void load(cursor), loading: more }}
      />
      <ConfirmDialog
        open={!!confirm} title={t("pages.deleteTitle")} object={confirm?.title} effect={t("pages.deleteEffect")}
        confirmLabel={t("pages.delete")} tone="danger" busy={busy} onConfirm={() => void doDelete()} onCancel={() => setConfirm(null)}
      />
    </div>
  );
}
