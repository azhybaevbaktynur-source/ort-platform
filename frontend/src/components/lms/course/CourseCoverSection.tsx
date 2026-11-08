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
import { LmsApiError } from "@/lib/lms/client";
import {
  COVER_ACCEPT, COVER_MAX_BYTES, COVER_MIN_HEIGHT, COVER_MIN_WIDTH, coverCropBox, isCoverType, removeCourseCover,
  uploadCourseCover,
} from "@/lib/lms/courseCover";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button, Card, ConfirmDialog, ErrorState, cn, focusRing } from "@/components/ui";
import { CourseCardCover } from "./CourseCardCover";

/** Error codes with a cover-specific text (`courses.cover.errors.<code>`); anything else: the general LMS text. */
const COVER_ERRORS = new Set([
  "image_type_unsupported", "image_too_small", "image_too_large", "payload_too_large", "image_invalid",
  "image_too_many_pixels", "platform_course_admin_only", "storage_full", "storage_quota_exceeded",
]);

interface Pending { file: File; url: string; width: number; height: number }

const STEP = 0.05;
const clamp01 = (v: number) => Math.min(Math.max(v, 0), 1);

/** Width and height of an image file as the browser shows it (oriented, like the server); null: not decodable. */
function readSize(url: string): Promise<{ width: number; height: number } | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

function FocusPicker({ pending, fx, fy, onChange }: {
  pending: Pending; fx: number; fy: number; onChange: (x: number, y: number) => void;
}) {
  const { t } = useTranslation();
  const wrap = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const { width: w, height: h } = pending;
  const box = coverCropBox(w, h, fx, fy);
  if (!box) return null;
  const slackX = (w - box.width) / w;
  const slackY = (h - box.height) / h;
  const axis: "x" | "y" | null = slackX >= slackY ? (w > box.width ? "x" : null) : (h > box.height ? "y" : null);
  const fw = box.width / w;
  const fh = box.height / h;

  /** Centre the frame on the pointer (clamped inside the image). */
  const moveTo = (clientX: number, clientY: number) => {
    const r = wrap.current?.getBoundingClientRect();
    if (!r || r.width === 0 || r.height === 0) return;
    const px = (clientX - r.left) / r.width;
    const py = (clientY - r.top) / r.height;
    const nx = fw < 1 ? clamp01((px - fw / 2) / (1 - fw)) : 0.5;
    const ny = fh < 1 ? clamp01((py - fh / 2) / (1 - fh)) : 0.5;
    onChange(nx, ny);
  };

  const value = axis === "y" ? fy : fx;
  const setValue = (v: number) => (axis === "y" ? onChange(fx, clamp01(v)) : onChange(clamp01(v), fy));
  const onKey = (e: React.KeyboardEvent) => {
    if (!axis) return;
    const next: Record<string, number> = {
      ArrowRight: value + STEP, ArrowDown: value + STEP, ArrowLeft: value - STEP, ArrowUp: value - STEP,
      PageDown: value + 4 * STEP, PageUp: value - 4 * STEP, Home: 0, End: 1,
    };
    if (e.key in next) {
      e.preventDefault();
      setValue(next[e.key]);
    }
  };
  const pct = Math.round(value * 100);

  return (
    <div>
      <p id="cover-focus-hint" className="mb-2 text-sm leading-6 text-slate-600">
        {axis ? t("courses.cover.focusHint") : t("courses.cover.alreadyWide")}
      </p>
      <div
        ref={wrap}
        data-testid="cover-focus-area"
        className={cn("relative mx-auto w-fit max-w-full select-none overflow-hidden rounded-xl bg-slate-900", axis && "cursor-move touch-none")}
        onPointerDown={(e) => {
          if (!axis) return;
          e.preventDefault();
          dragging.current = true;
          e.currentTarget.setPointerCapture(e.pointerId);
          moveTo(e.clientX, e.clientY);
        }}
        onPointerMove={(e) => { if (dragging.current) moveTo(e.clientX, e.clientY); }}
        onPointerUp={() => { dragging.current = false; }}
        onPointerCancel={() => { dragging.current = false; }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- a local object URL */}
        <img src={pending.url} alt="" draggable={false} className="block h-auto max-h-72 w-auto max-w-full" />
        <div
          role={axis ? "slider" : undefined}
          tabIndex={axis ? 0 : undefined}
          aria-label={axis ? t("courses.cover.focusLabel") : undefined}
          aria-describedby={axis ? "cover-focus-hint" : undefined}
          aria-orientation={axis ? (axis === "x" ? "horizontal" : "vertical") : undefined}
          aria-valuemin={axis ? 0 : undefined}
          aria-valuemax={axis ? 100 : undefined}
          aria-valuenow={axis ? pct : undefined}
          aria-valuetext={axis ? t(axis === "x" ? "courses.cover.focusValueX" : "courses.cover.focusValueY", { pct }) : undefined}
          onKeyDown={onKey}
          data-testid="cover-focus-frame"
          className={cn("absolute rounded-sm border-2 border-white shadow-[0_0_0_9999px_rgba(15,23,42,0.55)]", focusRing)}
          style={{
            left: `${(box.left / w) * 100}%`, top: `${(box.top / h) * 100}%`,
            width: `${fw * 100}%`, height: `${fh * 100}%`,
          }}
        />
      </div>
    </div>
  );
}

export function CourseCoverSection({ courseId, title, platform = false, coverUrl, onChanged, className }: {
  courseId: string;
  /** the course title in the viewer's language (the remove dialog names it) */
  title: string;
  /** a platform course: the default cover draws the platform mark, as on its cards */
  platform?: boolean;
  coverUrl: string | null | undefined;
  onChanged: (coverUrl: string | null) => void;
  className?: string;
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

  const fail = (code: string) => setError(new LmsApiError(0, code, code));

  const choose = async (file: File | undefined) => {
    setError(null);
    setSaved(null);
    if (!file) return;
    if (!isCoverType(file)) return fail("image_type_unsupported");
    if (file.size > COVER_MAX_BYTES) return fail("image_too_large");
    setBusy("check");
    const url = URL.createObjectURL(file);
    const size = await readSize(url);
    setBusy(null);
    if (!size) { URL.revokeObjectURL(url); return fail("image_invalid"); }
    if (size.width < COVER_MIN_WIDTH || size.height < COVER_MIN_HEIGHT) { URL.revokeObjectURL(url); return fail("image_too_small"); }
    setFx(0.5);
    setFy(0.5);
    setPending({ file, url, ...size });
  };

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

  const code = (error as { code?: string } | null)?.code;
  const errorView = !error ? null : code && COVER_ERRORS.has(code)
    ? <ErrorState variant="inline" message={t(`courses.cover.errors.${code}`)} />
    : <ErrorMessage error={error} />;

  return (
    <Card title={t("courses.cover.title")} description={t("courses.cover.hint")} className={className}>
      <div className="space-y-4" data-testid="course-cover-section">
        {pending ? (
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
