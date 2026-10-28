"use client";

// Phase 8a S4b: announcement composer (Markdown + server preview; "Post now" / "Save draft"; pin; stale `rev` -> conflict).
// There is no single-announcement GET route, so an existing one is found in the (cursor-paginated) staff list.
import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { createAnnouncement, getAnnouncement, publishAnnouncement, updateAnnouncement } from "@/lib/lms/announcements";
import { ANNOUNCEMENT_BODY_MAX, type AnnouncementStaffOut } from "@/lib/lms/pagesTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { ContentError } from "@/components/lms/pages/ApiError";
import { MarkdownField } from "@/components/lms/pages/MarkdownField";
import { Button, Dialog, EmptyState, Input, LoadingState, PageHeader, Switch, toast } from "@/components/ui";

async function findAnnouncement(courseId: string, id: string): Promise<AnnouncementStaffOut | null> {
  // Phase 8a S5: the single-announcement route (S3); 404 = deleted or not in this course
  try {
    return (await getAnnouncement(courseId, id)) as AnnouncementStaffOut;
  } catch (e) {
    if ((e as { status?: number }).status === 404) return null;
    throw e;
  }
}

export function AnnouncementEditor({ announcementId }: { announcementId?: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const back = `/${lang}/courses/${course.id}/announcements`;
  const [item, setItem] = useState<AnnouncementStaffOut | null>(null);
  const [loading, setLoading] = useState(!!announcementId);
  const [missing, setMissing] = useState(false);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [pinned, setPinned] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [conflict, setConflict] = useState(false);
  const [dirty, setDirty] = useState(false);

  const apply = (a: AnnouncementStaffOut) => { setItem(a); setTitle(a.title); setBody(a.body_md); setPinned(a.pinned); setDirty(false); };

  useEffect(() => {
    if (!announcementId) return;
    let live = true;
    findAnnouncement(course.id, announcementId)
      .then((a) => { if (!live) return; if (a) apply(a); else setMissing(true); })
      .catch((e) => { if (live) setLoadError(e); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [course.id, announcementId]);

  useEffect(() => {
    if (!dirty) return;
    const h = (ev: BeforeUnloadEvent) => { ev.preventDefault(); };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  const valid = title.trim().length > 0 && body.length <= ANNOUNCEMENT_BODY_MAX;

  const submit = async (postNow: boolean, rev?: number) => {
    if (!valid) return;
    setBusy(true); setError(null);
    try {
      if (!item) {
        await createAnnouncement(course.id, { title: title.trim(), body_md: body, pinned, publish: postNow });
        toast.success(t(postNow ? "announcements.posted" : "announcements.draftSaved"));
      } else {
        const saved = await updateAnnouncement(course.id, item.id, { rev: rev ?? item.rev, title: title.trim(), body_md: body, pinned });
        if (postNow && !saved.published_at) await publishAnnouncement(course.id, item.id);
        toast.success(t(postNow ? "announcements.posted" : "announcements.saved"));
      }
      setDirty(false);
      router.push(back);
    } catch (e) {
      if ((e as { code?: string }).code === "page_conflict") setConflict(true);
      else setError(e);
    } finally { setBusy(false); }
  };

  const reload = async () => {
    if (!item) return;
    setConflict(false);
    try { const a = await findAnnouncement(course.id, item.id); if (a) apply(a); else setMissing(true); } catch (e) { setError(e); }
  };
  const overwrite = async () => {
    if (!item) return;
    setConflict(false);
    try { const a = await findAnnouncement(course.id, item.id); if (a) await submit(false, a.rev); } catch (e) { setError(e); }
  };

  if (loading) return <LoadingState />;
  if (loadError) return <ContentError error={loadError} />;
  if (missing) return <EmptyState title={t("announcements.notFound")} />;
  const isDraft = !item || !item.published_at;

  return (
    <div className="max-w-3xl">
      <PageHeader
        title={t(item ? "announcements.editTitle" : "announcements.newTitle")}
        breadcrumbs={[{ label: t("announcements.title"), href: back }, { label: t(item ? "announcements.editTitle" : "announcements.newTitle") }]}
      />
      <div className="space-y-5">
        <ContentError error={error} />
        <Input label={t("announcements.fieldTitle")} value={title} maxLength={300} onChange={(ev) => { setTitle(ev.target.value); setDirty(true); }} />
        <Switch label={t("announcements.fieldPinned")} hint={t("announcements.pinnedHint")} checked={pinned} onChange={(v) => { setPinned(v); setDirty(true); }} />
        <MarkdownField courseId={course.id} label={t("announcements.fieldBody")} value={body} max={ANNOUNCEMENT_BODY_MAX} rows={10} onChange={(v) => { setBody(v); setDirty(true); }} />
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          {isDraft ? (
            <>
              <Button variant="secondary" onClick={() => void submit(false)} disabled={!valid || busy}>{t("announcements.saveDraft")}</Button>
              <Button onClick={() => void submit(true)} loading={busy} disabled={!valid}>{t("announcements.postNow")}</Button>
            </>
          ) : (
            <Button onClick={() => void submit(false)} loading={busy} disabled={!valid}>{t("common.save")}</Button>
          )}
        </div>
      </div>
      <Dialog
        open={conflict} onClose={() => setConflict(false)} title={t("pages.conflict.title")} description={t("pages.conflict.body")}
        footer={<>
          <Button variant="secondary" onClick={() => setConflict(false)}>{t("pages.conflict.keep")}</Button>
          <Button variant="secondary" onClick={() => void overwrite()}>{t("pages.conflict.overwrite")}</Button>
          <Button onClick={() => void reload()}>{t("pages.conflict.reload")}</Button>
        </>}
      />
    </div>
  );
}
