"use client";

// Phase 8a S4b: Announcements tab. Students: published list (pinned first, newest first, paginated). Staff: the same plus
// a Drafts section, compose button and per-row edit / post / delete.
import React, { useCallback, useEffect, useState } from "react";
import { Megaphone, Pin, Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { deleteAnnouncement, listAnnouncements, publishAnnouncement } from "@/lib/lms/announcements";
import type { AnnouncementStaffOut, AnnouncementStudentOut } from "@/lib/lms/pagesTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { ContentError } from "@/components/lms/pages/ApiError";
import { SafeHtml } from "@/components/lms/pages/SafeHtml";
import { Badge, Button, ConfirmDialog, EmptyState, LinkButton, LoadingState, PageHeader, Pagination, toast } from "@/components/ui";

type Row = AnnouncementStaffOut | AnnouncementStudentOut;
const isStaffRow = (r: Row): r is AnnouncementStaffOut => "rev" in r;

export function AnnouncementsView() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const base = `/${lang}/courses/${course.id}/announcements`;
  const [items, setItems] = useState<Row[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<AnnouncementStaffOut | null>(null);

  const load = useCallback(async (next?: string | null) => {
    if (next) setMore(true); else setLoading(true);
    setError(null);
    try {
      const page = await listAnnouncements(course.id, { cursor: next, limit: 20 });
      setItems((p) => (next ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) { setError(e); } finally { setLoading(false); setMore(false); }
  }, [course.id]);
  useEffect(() => { void load(); }, [load]);

  const post = async (a: AnnouncementStaffOut) => {
    setBusyId(a.id); setActionError(null);
    try { await publishAnnouncement(course.id, a.id); toast.success(t("announcements.posted")); await load(); }
    catch (e) { setActionError(e); } finally { setBusyId(null); }
  };
  const doDelete = async () => {
    if (!confirm) return;
    setBusyId(confirm.id); setActionError(null);
    try { await deleteAnnouncement(course.id, confirm.id); setConfirm(null); await load(); }
    catch (e) { setConfirm(null); setActionError(e); } finally { setBusyId(null); }
  };

  const drafts = items.filter((r) => isStaffRow(r) && !r.published_at) as AnnouncementStaffOut[];
  const published = items.filter((r) => !isStaffRow(r) || r.published_at);

  const card = (r: Row) => {
    const staff = isStaffRow(r) ? r : null;
    return (
      <li key={r.id} className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h3 className="min-w-0 break-words text-base font-semibold text-slate-900">{r.title}</h3>
          <div className="flex items-center gap-2">
            {r.pinned && <Badge tone="info"><Pin className="mr-1 inline h-3 w-3" aria-hidden="true" />{t("announcements.pinned")}</Badge>}
            {staff && !staff.published_at && <Badge tone="neutral">{t("announcements.draft")}</Badge>}
          </div>
        </div>
        <p className="mt-0.5 text-xs text-slate-600">
          {r.published_at ? t("announcements.byOn", { author: r.author_name, date: fmtShortDateTime(r.published_at, lang) }) : t("announcements.byDraft", { author: r.author_name })}
        </p>
        {r.body_html && <SafeHtml html={r.body_html} className="mt-3" />}
        {canEdit && staff && (
          <div className="mt-4 flex flex-wrap gap-2">
            <LinkButton href={`${base}/${r.id}/edit`} variant="secondary" size="sm">{t("announcements.edit")}</LinkButton>
            {!staff.published_at && <Button size="sm" loading={busyId === r.id} onClick={() => void post(staff)}>{t("announcements.postNow")}</Button>}
            <Button variant="danger" size="sm" onClick={() => setConfirm(staff)}>{t("announcements.delete")}</Button>
          </div>
        )}
      </li>
    );
  };

  return (
    <div>
      <PageHeader
        title={t("announcements.title")}
        description={t(canEdit ? "announcements.descriptionStaff" : "announcements.descriptionStudent")}
        primaryAction={canEdit ? <LinkButton href={`${base}/new`} leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}>{t("announcements.new")}</LinkButton> : undefined}
      />
      <ContentError error={actionError} className="mb-4" />
      {loading ? <LoadingState /> : error ? <ContentError error={error} onRetry={() => void load()} /> : items.length === 0 ? (
        <EmptyState title={t("announcements.empty")} description={t(canEdit ? "announcements.emptyHintStaff" : "announcements.emptyHintStudent")}
          icon={<Megaphone className="h-6 w-6" aria-hidden="true" />}
          action={canEdit ? <LinkButton href={`${base}/new`}>{t("announcements.new")}</LinkButton> : undefined} />
      ) : (
        <div className="space-y-8">
          {drafts.length > 0 && (
            <section aria-labelledby="ann-drafts">
              <h2 id="ann-drafts" className="mb-3 text-sm font-semibold text-slate-800">{t("announcements.drafts")}</h2>
              <ul className="space-y-3">{drafts.map(card)}</ul>
            </section>
          )}
          {published.length > 0 && (
            <section aria-labelledby="ann-posted">
              {canEdit && <h2 id="ann-posted" className="mb-3 text-sm font-semibold text-slate-800">{t("announcements.listPosted")}</h2>}
              <ul className="space-y-3">{published.map(card)}</ul>
            </section>
          )}
        </div>
      )}
      <Pagination nextCursor={cursor} onLoadMore={() => void load(cursor)} loading={more} />
      <ConfirmDialog
        open={!!confirm} title={t("announcements.deleteTitle")} object={confirm?.title} effect={t("announcements.deleteEffect")}
        confirmLabel={t("announcements.delete")} tone="danger" busy={!!busyId && busyId === confirm?.id}
        onConfirm={() => void doDelete()} onCancel={() => setConfirm(null)}
      />
    </div>
  );
}
