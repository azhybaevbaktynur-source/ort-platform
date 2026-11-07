// F7b (STUDENT_UI_FIX_PLAN 7.1): course cover upload and removal, the client-side checks and the server's crop box.
import { getAuthHeader } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";
import { LmsApiError, lmsFetch } from "./client";
import type { CourseCoverOut } from "./types";

const enc = encodeURIComponent;

/** The server's limits (`ASSET_MAX_UPLOAD_BYTES`, `files/images.py` COVER_MIN_*). */
export const COVER_MAX_BYTES = 2 * 1024 * 1024;
export const COVER_MIN_WIDTH = 320;
export const COVER_MIN_HEIGHT = 180;
export const COVER_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;
export const COVER_ACCEPT = ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp";

/** The type by MIME, else by extension (some systems send an empty type). */
export function isCoverType(file: { type: string; name: string }): boolean {
  if (file.type) return (COVER_TYPES as readonly string[]).includes(file.type);
  return /\.(jpe?g|png|webp)$/i.test(file.name);
}

export interface CropBox { left: number; top: number; width: number; height: number }

/** The exact box `files.images.cover_crop_box` keeps: the largest 16:9 box (a multiple of 16 x 9) inside the image,
 * placed by the focus (0..1 on each axis). Null for an image smaller than 16 x 9. */
export function coverCropBox(width: number, height: number, focusX = 0.5, focusY = 0.5): CropBox | null {
  const units = Math.min(Math.floor(width / 16), Math.floor(height / 9));
  if (units < 1) return null;
  const cw = units * 16;
  const ch = units * 9;
  const fx = Math.min(Math.max(focusX, 0), 1);
  const fy = Math.min(Math.max(focusY, 0), 1);
  return { left: Math.round((width - cw) * fx), top: Math.round((height - ch) * fy), width: cw, height: ch };
}

/** `POST /courses/{id}/cover`: multipart `file` + `focus_x` / `focus_y`; errors parsed like `lmsFetch`. */
export async function uploadCourseCover(courseId: string, file: File, focusX: number, focusY: number): Promise<CourseCoverOut> {
  const form = new FormData();
  form.append("file", file);
  form.append("focus_x", focusX.toFixed(3));
  form.append("focus_y", focusY.toFixed(3));
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/courses/${enc(courseId)}/cover`, {
      method: "POST",
      headers: { ...(await getAuthHeader()) },
      body: form,
      cache: "no-store",
    });
  } catch {
    throw new LmsApiError(0, "network", "Network error");
  }
  const text = await res.text();
  let data: unknown = undefined;
  if (text) {
    try { data = JSON.parse(text); } catch { data = undefined; }
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | undefined)?.error;
    if (err && typeof err === "object" && typeof err.code === "string") {
      throw new LmsApiError(res.status, err.code, err.message || err.code, err.details || {});
    }
    const code = res.status === 413 ? "image_too_large" : res.status === 403 ? "forbidden" : res.status === 404 ? "not_found" : "unknown";
    throw new LmsApiError(res.status, code, `HTTP ${res.status}`);
  }
  return data as CourseCoverOut;
}

/** `DELETE /courses/{id}/cover` (idempotent). */
export const removeCourseCover = (courseId: string) =>
  lmsFetch<void>(`/courses/${enc(courseId)}/cover`, { method: "DELETE" });
