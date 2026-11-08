"use client";

/*
 * FB8-5 S3 (STAFF_UX_AUDIT 4): the cover picked before the course exists. The file stays in the browser (checked like
 * the settings section: type, size, at least 320 x 180) with the same 16:9 focus frame; the create page uploads it
 * right after the course is made. The shared pieces (file check, focus frame, error text) live here and the settings
 * section (`CourseCoverSection`) imports them.
 */
import React, { useEffect, useRef, useState } from "react";
import { ImageUp, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { LmsApiError } from "@/lib/lms/client";
import { COVER_ACCEPT, COVER_MAX_BYTES, COVER_MIN_HEIGHT, COVER_MIN_WIDTH, coverCropBox, isCoverType } from "@/lib/lms/courseCover";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button, ErrorState, cn, focusRing } from "@/components/ui";

/** Error codes with a cover-specific text (`courses.cover.errors.<code>`); anything else: the general LMS text. */
export const COVER_ERRORS = new Set([
  "image_type_unsupported", "image_too_small", "image_too_large", "payload_too_large", "image_invalid",
  "image_too_many_pixels", "platform_course_admin_only", "storage_full", "storage_quota_exceeded",
]);

/** A chosen image (object URL) and its focus; `fx` / `fy` 0..1 as the server's `focus_x` / `focus_y`. */
export interface PendingCover { file: File; url: string; width: number; height: number; fx: number; fy: number }

/** What a preview needs to draw a pending cover the way the server will crop it. */
export interface CoverPreview { url: string; fx: number; fy: number }

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

/** The client checks; a usable file comes back with a fresh object URL (the caller revokes it), else an error code. */
export async function checkCoverFile(file: File): Promise<{ pending: PendingCover } | { code: string }> {
  if (!isCoverType(file)) return { code: "image_type_unsupported" };
  if (file.size > COVER_MAX_BYTES) return { code: "image_too_large" };
  const url = URL.createObjectURL(file);
  const size = await readSize(url);
  if (!size) { URL.revokeObjectURL(url); return { code: "image_invalid" }; }
  if (size.width < COVER_MIN_WIDTH || size.height < COVER_MIN_HEIGHT) { URL.revokeObjectURL(url); return { code: "image_too_small" }; }
  return { pending: { file, url, ...size, fx: 0.5, fy: 0.5 } };
}

export const coverCodeError = (code: string) => new LmsApiError(0, code, code);

/** The cover-specific text of an error, or the general one. */
export function CoverErrorView({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (!error) return null;
  const code = (error as { code?: string } | null)?.code;
  return code && COVER_ERRORS.has(code)
    ? <ErrorState variant="inline" message={t(`courses.cover.errors.${code}`)} />
    : <ErrorMessage error={error} />;
}

/** The 16:9 frame over the source image: drag, click or arrow keys (a slider along the axis that has slack). */
export function FocusPicker({ pending, fx, fy, onChange }: {
  pending: { url: string; width: number; height: number }; fx: number; fy: number; onChange: (x: number, y: number) => void;
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

/** The create form's cover field: choose, frame, take back; nothing is sent until the course exists. */
export function CoverPicker({ value, onChange, disabled }: {
  value: PendingCover | null;
  onChange: (v: PendingCover | null) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const url = value?.url;
  // the object URL lives as long as the chosen file
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  const choose = async (file: File | undefined) => {
    setError(null);
    if (!file) return;
    setChecking(true);
    const out = await checkCoverFile(file);
    setChecking(false);
    if ("code" in out) return setError(coverCodeError(out.code));
    onChange(out.pending);
  };

  return (
    <div className="space-y-3" data-testid="cover-picker">
      <p className="text-sm leading-6 text-slate-600">{value ? t("courses.create.coverChosen") : t("courses.create.coverDefault")}</p>
      {value && (
        <FocusPicker pending={value} fx={value.fx} fy={value.fy} onChange={(fx, fy) => onChange({ ...value, fx, fy })} />
      )}
      <input ref={input} id="new-cover-file" type="file" accept={COVER_ACCEPT} className="sr-only" tabIndex={-1}
        aria-hidden="true" data-testid="cover-file"
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; void choose(f); }} />
      <CoverErrorView error={error} />
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="secondary" loading={checking} disabled={disabled}
          leftIcon={<ImageUp aria-hidden="true" className="h-4 w-4" />} onClick={() => input.current?.click()}>
          {value ? t("courses.cover.replace") : t("courses.cover.choose")}
        </Button>
        {value && (
          <Button size="sm" variant="secondary" disabled={disabled} leftIcon={<X aria-hidden="true" className="h-4 w-4" />}
            onClick={() => { setError(null); onChange(null); }}>
            {t("courses.create.coverUseDefault")}
          </Button>
        )}
      </div>
      <p className="text-xs leading-5 text-slate-500">{t("courses.cover.limits")}</p>
    </div>
  );
}
