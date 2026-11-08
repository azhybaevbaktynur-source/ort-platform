"use client";

/*
 * F7b (STUDENT_UI_FIX_PLAN 7.1): the "Course cover" settings section, in the teacher's course settings and on the
 * platform admin's page of a platform course. The current cover (or the generated default), a JPG/PNG/WebP up to
 * 2 MB checked here first (type, size, at least 320 x 180), a focus picker on the source image whose frame is the
 * exact 16:9 box the server keeps (`coverCropBox` = `files.images.cover_crop_box`), save and remove (confirmed).
 */
import React, { useEffect, useRef, useState } from "react";
import { ImageUp, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { COVER_ACCEPT, removeCourseCover, uploadCourseCover } from "@/lib/lms/courseCover";
import { Button, Card, ConfirmDialog } from "@/components/ui";
import { CourseCardCover } from "./CourseCardCover";
import { CoverErrorView, FocusPicker, checkCoverFile, coverCodeError, type CoverPreview } from "./form/CoverPicker"; // FB8-5 S3

interface Pending { file: File; url: string; width: number; height: number }

export function CourseCoverSection({ courseId, title, platform = false, coverUrl, onChanged, className, previews = true, onPreview }: {
  courseId: string;
  /** the course title in the viewer's language (the remove dialog names it) */
  title: string;
  /** a platform course: the default cover draws the platform mark, as on its cards */
  platform?: boolean;
  coverUrl: string | null | undefined;
  onChanged: (coverUrl: string | null) => void;
  className?: string;
  /** FB8-5 S3: false where a card preview sits beside the section (course settings): no own card/banner previews */
  previews?: boolean;
  /** FB8-5 S3: the chosen, not yet saved image and its focus (null when there is none), for that side preview */
  onPreview?: (p: CoverPreview | null) => void;
}) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [fx, setFx] = useState(0.5);
  const [fy, setFy] = useState(0.5);
  const [busy, setBusy] = useState<null | "check" | "save" | "remove">(null);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState<null | "saved" | "removed">(null);
  const [confirmRemove, setConfirmRemove] = useState(false);

  // the object URL lives as long as the pending file
  useEffect(() => () => { if (pending) URL.revokeObjectURL(pending.url); }, [pending]);

  const fail = (code: string) => setError(coverCodeError(code));

  const choose = async (file: File | undefined) => {
    setError(null);
    setSaved(null);
    if (!file) return;
    setBusy("check");
    const out = await checkCoverFile(file);
    setBusy(null);
    if ("code" in out) return fail(out.code);
    const { fx: x, fy: y, ...p } = out.pending;
    setFx(x);
    setFy(y);
    setPending(p);
  };

  // FB8-5 S3: tell the side preview what to draw
  useEffect(() => { onPreview?.(pending ? { url: pending.url, fx, fy } : null); }, [pending, fx, fy, onPreview]);

  const save = async () => {
    if (!pending) return;
    setBusy("save");
    setError(null);
    try {
      const out = await uploadCourseCover(courseId, pending.file, fx, fy);
      setPending(null);
      setSaved("saved");
      onChanged(out.cover_url);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    setBusy("remove");
    setError(null);
    try {
      await removeCourseCover(courseId);
      setConfirmRemove(false);
      setSaved("removed");
      onChanged(null);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const errorView = error ? <CoverErrorView error={error} /> : null;

  return (
    <Card title={t("courses.cover.title")} description={t("courses.cover.hint")} className={className}>
      <div className="space-y-4" data-testid="course-cover-section">
        {!previews ? (
          // FB8-5 S3: the card beside the section previews; here only the state in words
          <p className="text-sm font-medium text-slate-700" data-testid="cover-current" data-cover-url={coverUrl ?? ""}>
            {pending ? t("courses.cover.preview") : coverUrl ? t("courses.cover.current") : t("courses.cover.default")}
          </p>
        ) : pending ? (
          // two previews of the chosen frame: the 16:9 card and the course page banner (StudentSyllabus' aspect classes)
          <div className="space-y-4">
            <p className="text-sm font-medium text-slate-700">{t("courses.cover.preview")}</p>
            <div className="max-w-[360px]">
              <p className="mb-2 text-sm text-slate-600">{t("courses.cover.previewCard")}</p>
              <div className="relative h-[150px] overflow-hidden rounded-xl border border-slate-200 bg-slate-100">
                {/* eslint-disable-next-line @next/next/no-img-element -- a local object URL; object-position = the server's crop */}
                <img src={pending.url} alt={t("courses.cover.previewAlt")} data-testid="cover-preview"
                  className="absolute inset-0 h-full w-full object-cover" style={{ objectPosition: `${fx * 100}% ${fy * 100}%` }} />
              </div>
            </div>
            <div className="max-w-3xl">
              <p className="mb-2 text-sm text-slate-600">{t("courses.cover.previewBanner")}</p>
              <div className="relative aspect-[16/9] overflow-hidden rounded-xl border border-slate-200 bg-slate-100 sm:aspect-[3/1] lg:aspect-[5/1]">
                {/* eslint-disable-next-line @next/next/no-img-element -- the same object URL, framed like the banner */}
                <img src={pending.url} alt="" data-testid="cover-preview-banner"
                  className="absolute inset-0 h-full w-full object-cover" style={{ objectPosition: `${fx * 100}% ${fy * 100}%` }} />
              </div>
            </div>
          </div>
        ) : (
          <div className="max-w-[360px]">
            <p className="mb-2 text-sm font-medium text-slate-700">{coverUrl ? t("courses.cover.current") : t("courses.cover.default")}</p>
            <div data-testid="cover-current" data-cover-url={coverUrl ?? ""}>
              <CourseCardCover card courseId={courseId} platform={platform} coverUrl={coverUrl} className="rounded-xl border border-slate-200" />
            </div>
          </div>
        )}

        {pending && <FocusPicker pending={pending} fx={fx} fy={fy} onChange={(x, y) => { setFx(x); setFy(y); }} />}

        <input ref={input} id={`cover-file-${courseId}`} type="file" accept={COVER_ACCEPT} className="sr-only" tabIndex={-1}
          aria-hidden="true" data-testid="cover-file"
          onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; void choose(f); }} />

        {!confirmRemove && errorView}

        <div className="flex flex-wrap items-center gap-2">
          {pending ? (
            <>
              <Button size="sm" loading={busy === "save"} onClick={() => void save()}>{t("courses.cover.save")}</Button>
              <Button size="sm" variant="secondary" disabled={busy === "save"} onClick={() => { setPending(null); setError(null); }}>
                {t("lms.common.cancel")}
              </Button>
            </>
          ) : (
            <>
              <Button size="sm" variant="secondary" loading={busy === "check"} disabled={busy !== null && busy !== "check"}
                leftIcon={<ImageUp aria-hidden="true" className="h-4 w-4" />} onClick={() => input.current?.click()}>
                {coverUrl ? t("courses.cover.replace") : t("courses.cover.choose")}
              </Button>
              {coverUrl && (
                <Button size="sm" variant="secondary" disabled={busy !== null}
                  className="border-danger-300 text-danger-700 hover:bg-danger-50"
                  leftIcon={<Trash2 aria-hidden="true" className="h-4 w-4" />}
                  onClick={() => { setError(null); setSaved(null); setConfirmRemove(true); }}>
                  {t("courses.cover.remove")}
                </Button>
              )}
            </>
          )}
          {saved && <p role="status" className="text-sm text-success-700">{t(saved === "saved" ? "courses.cover.savedMsg" : "courses.cover.removedMsg")}</p>}
        </div>
        <p className="text-xs leading-5 text-slate-500">{t("courses.cover.limits")}</p>
      </div>

      {confirmRemove && (
        <ConfirmDialog open tone="danger" busy={busy === "remove"} title={t("courses.cover.removeTitle")} object={title}
          effect={t("courses.cover.removeBody")} confirmLabel={t("courses.cover.remove")}
          error={error ? errorView : undefined}
          onConfirm={() => void remove()} onCancel={() => { setConfirmRemove(false); setError(null); }} />
      )}
    </Card>
  );
}
