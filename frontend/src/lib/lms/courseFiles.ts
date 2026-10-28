// Phase 8a S4b: course files API client (design 7.2, 5.3). Types in pagesTypes.ts.
import { getAuthHeader } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";
import { LmsApiError, lmsFetch } from "./client";
import type { CourseFilesPageOut, CourseFileStaffOut, CourseFileUpdateIn, DownloadOut } from "./pagesTypes";

const e = encodeURIComponent;
const base = (c: string) => `/courses/${e(c)}/course-files`;

export const listCourseFiles = (courseId: string, q: { cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<CourseFilesPageOut>(base(courseId), { params: { cursor: q.cursor, limit: q.limit } });
export const updateCourseFile = (courseId: string, fileId: string, body: CourseFileUpdateIn) =>
  lmsFetch<CourseFileStaffOut>(`${base(courseId)}/${e(fileId)}`, { method: "PATCH", body });
export const deleteCourseFile = (courseId: string, fileId: string) =>
  lmsFetch<void>(`${base(courseId)}/${e(fileId)}`, { method: "DELETE" });
const getDownload = (courseId: string, fileId: string) => lmsFetch<DownloadOut>(`${base(courseId)}/${e(fileId)}/download`);

function toError(status: number, text: string): LmsApiError {
  let data: { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | undefined;
  try { data = text ? JSON.parse(text) : undefined; } catch { data = undefined; }
  const err = data?.error;
  if (err && typeof err.code === "string") return new LmsApiError(status, err.code, err.message || err.code, err.details || {});
  const code = status === 413 ? "payload_too_large" : status === 507 ? "storage_full" : status === 403 ? "forbidden" : status === 404 ? "not_found" : "unknown";
  return new LmsApiError(status, code, `HTTP ${status}`);
}

/** Multipart upload with progress (XMLHttpRequest). `onProgress` gets 0..1. */
export async function uploadCourseFile(
  courseId: string,
  input: { file: File; folder: string; title: string; published: boolean },
  onProgress?: (ratio: number) => void,
): Promise<CourseFileStaffOut> {
  const headers = await getAuthHeader();
  return new Promise<CourseFileStaffOut>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}${base(courseId)}`);
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (ev) => { if (ev.lengthComputable && onProgress) onProgress(ev.loaded / ev.total); };
    xhr.onerror = () => reject(new LmsApiError(0, "network", "Network error"));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText) as CourseFileStaffOut); } catch { reject(new LmsApiError(500, "unknown", "Bad response")); }
      } else reject(toError(xhr.status, xhr.responseText));
    };
    const form = new FormData();
    form.append("file", input.file);
    form.append("folder", input.folder);
    form.append("title", input.title);
    form.append("published", input.published ? "true" : "false");
    xhr.send(form);
  });
}

/**
 * Fetches the download `{url}` (after the module gate; 423 surfaces as LmsApiError) and hands the file to the browser.
 * A presigned R2 link is opened by navigation; the db/local driver's authenticated content route is fetched with the
 * bearer token and saved as an object URL.
 */
export async function downloadCourseFile(courseId: string, fileId: string, filename?: string | null): Promise<void> {
  const { url } = await getDownload(courseId, fileId);
  const api = new URL(API_BASE_URL, window.location.origin);
  const target = new URL(url, api);
  if (target.origin !== api.origin) { window.location.assign(target.toString()); return; }
  let res: Response;
  try { res = await fetch(target.toString(), { headers: { ...(await getAuthHeader()) }, cache: "no-store" }); }
  catch { throw new LmsApiError(0, "network", "Network error"); }
  if (!res.ok) throw toError(res.status, await res.text());
  const objectUrl = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = objectUrl;
  a.rel = "noopener";
  a.download = filename || "file.pdf";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}
