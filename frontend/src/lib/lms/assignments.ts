// Phase 7a S5: assignments API client (docs/phases/PHASE_7A_DESIGN.md sections 4.1-4.3). Types in assignmentTypes.ts.
import { getAuthHeader } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";
import { LmsApiError, lmsFetch } from "./client";
import type { PageOut } from "./types";
import type { ReleaseIn, ReleaseOut, RegradeOut, UnreleaseOut } from "./gradingTypes";
import type {
  AssignmentCreateIn, AssignmentListQuery, AssignmentOut, AssignmentStaffOut, AssignmentStaffSummaryOut,
  AssignmentStudentDetailOut, AssignmentStudentOut, AssignmentSubmissionRowOut, AssignmentSubmissionStaffOut,
  AssignmentUpdateIn, HandInIn, HandInOut, ManualGradeIn, RubricCriterionIn, RubricCriterionOut, UploadedFileOut,
} from "./assignmentTypes";

export { quizAssignmentId } from "./quizAssignmentId";

const e = encodeURIComponent;
const course = (c: string) => `/courses/${e(c)}`;
const list = (c: string) => `${course(c)}/assignments`;
const one = (c: string, a: string) => `${list(c)}/${e(a)}`;

// ---- 4.1 Assignments ----
export const listAssignments = (courseId: string, q: AssignmentListQuery = {}) =>
  lmsFetch<PageOut<AssignmentStaffSummaryOut | AssignmentStudentOut>>(list(courseId), {
    params: {
      cursor: q.cursor, limit: q.limit, deleted: q.deleted, kind: q.kind || undefined,
      published: q.published, category_id: q.category_id ?? undefined,
    },
  });
export const createAssignment = (courseId: string, body: AssignmentCreateIn) =>
  lmsFetch<AssignmentStaffOut>(list(courseId), { method: "POST", body });
export const getAssignment = (courseId: string, assignmentId: string) => lmsFetch<AssignmentOut>(one(courseId, assignmentId));
export const getStaffAssignment = (courseId: string, assignmentId: string) =>
  lmsFetch<AssignmentStaffOut>(one(courseId, assignmentId));
export const updateAssignment = (courseId: string, assignmentId: string, body: AssignmentUpdateIn) =>
  lmsFetch<AssignmentStaffOut>(one(courseId, assignmentId), { method: "PATCH", body });
export const deleteAssignment = (courseId: string, assignmentId: string) =>
  lmsFetch<void>(one(courseId, assignmentId), { method: "DELETE" });
export const restoreAssignment = (courseId: string, assignmentId: string) =>
  lmsFetch<AssignmentStaffOut>(`${one(courseId, assignmentId)}/restore`, { method: "POST" });
export const reorderAssignments = (courseId: string, assignmentIds: string[]) =>
  lmsFetch<unknown>(`${list(courseId)}/order`, { method: "PUT", body: { assignment_ids: assignmentIds } });
export const putRubric = (courseId: string, assignmentId: string, criteria: RubricCriterionIn[]) =>
  lmsFetch<RubricCriterionOut[] | { rubric: RubricCriterionOut[] }>(`${one(courseId, assignmentId)}/rubric`, { method: "PUT", body: criteria });

// ---- 4.2 Hand-ins and files ----
export const getMyAssignment = (courseId: string, assignmentId: string) =>
  lmsFetch<AssignmentStudentDetailOut>(`${one(courseId, assignmentId)}/mine`);
export const handIn = (courseId: string, assignmentId: string, body: HandInIn) =>
  lmsFetch<HandInOut>(`${one(courseId, assignmentId)}/submissions`, { method: "POST", body });

function parseError(res: Response, data: unknown): LmsApiError {
  const err = (data as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | undefined)?.error;
  if (err && typeof err === "object" && typeof err.code === "string") {
    return new LmsApiError(res.status, err.code, err.message || err.code, err.details || {});
  }
  const code = res.status === 413 ? "file_too_large" : res.status === 507 ? "storage_full" : res.status === 403 ? "forbidden"
    : res.status === 404 ? "not_found" : "unknown";
  return new LmsApiError(res.status, code, `HTTP ${res.status}`);
}

/**
 * Multipart upload with progress (XMLHttpRequest: fetch has no upload progress). Errors are LmsApiError like lmsFetch.
 * `onProgress` gets 0..1.
 */
async function uploadMultipart<T>(path: string, file: File, onProgress?: (ratio: number) => void, signal?: AbortSignal): Promise<T> {
  const headers = await getAuthHeader();
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}${path}`);
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (ev) => { if (ev.lengthComputable && onProgress) onProgress(ev.loaded / ev.total); };
    xhr.onerror = () => reject(new LmsApiError(0, "network", "Network error"));
    xhr.onabort = () => reject(new DOMException("Aborted", "AbortError"));
    xhr.onload = () => {
      let data: unknown = undefined;
      try { data = xhr.responseText ? JSON.parse(xhr.responseText) : undefined; } catch { data = undefined; }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as T);
      else reject(parseError({ status: xhr.status } as Response, data));
    };
    signal?.addEventListener("abort", () => xhr.abort());
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export const uploadHandInFile = (courseId: string, assignmentId: string, file: File, onProgress?: (r: number) => void, signal?: AbortSignal) =>
  uploadMultipart<UploadedFileOut>(`${one(courseId, assignmentId)}/submissions/files`, file, onProgress, signal);
export const uploadFeedbackFile = (courseId: string, assignmentId: string, file: File, onProgress?: (r: number) => void) =>
  uploadMultipart<UploadedFileOut>(`${one(courseId, assignmentId)}/feedback-files`, file, onProgress);

/**
 * Opens a hand-in or feedback file (owner and course staff only; section 4.2). The route needs the bearer token,
 * so the file is fetched and handed to the browser as an object URL. A JSON body `{url}` (presigned link) is opened directly.
 */
export async function openSubmissionFile(courseId: string, submissionId: string, assetId: string, filename?: string | null): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${course(courseId)}/submissions/${e(submissionId)}/files/${e(assetId)}`, {
      headers: { ...(await getAuthHeader()) },
      cache: "no-store",
    });
  } catch {
    throw new LmsApiError(0, "network", "Network error");
  }
  if (!res.ok) {
    let data: unknown = undefined;
    try { data = JSON.parse(await res.text()); } catch { data = undefined; }
    throw parseError(res, data);
  }
  const type = res.headers.get("content-type") || "";
  if (type.includes("application/json")) {
    const body = (await res.json()) as { url?: string };
    if (body.url) { window.open(body.url, "_blank", "noopener"); return; }
    throw new LmsApiError(500, "unknown", "No file url");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.rel = "noopener";
  if (filename) a.download = filename;
  else a.target = "_blank";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

// ---- 4.3 Grades ----
export const listAssignmentSubmissions = (courseId: string, assignmentId: string, opts: { cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<AssignmentSubmissionRowOut>>(`${one(courseId, assignmentId)}/submissions`, { params: { cursor: opts.cursor, limit: opts.limit } });
export const getAssignmentSubmission = (courseId: string, submissionId: string) =>
  lmsFetch<AssignmentSubmissionStaffOut>(`${course(courseId)}/submissions/${e(submissionId)}`);
export const gradeManual = (courseId: string, assignmentId: string, enrollmentId: string, body: ManualGradeIn) =>
  lmsFetch<AssignmentSubmissionStaffOut>(`${one(courseId, assignmentId)}/grades/${e(enrollmentId)}`, { method: "PUT", body });

const grades = (c: string, a: string) => `${one(c, a)}/grades`;
export const releaseAssignmentGrades = (courseId: string, assignmentId: string, body: ReleaseIn = {}) =>
  lmsFetch<ReleaseOut>(`${grades(courseId, assignmentId)}/release`, { method: "POST", body });
export const unreleaseAssignmentGrades = (courseId: string, assignmentId: string, body: ReleaseIn = {}) =>
  lmsFetch<UnreleaseOut>(`${grades(courseId, assignmentId)}/unrelease`, { method: "POST", body });
export const regradeAssignment = (courseId: string, assignmentId: string) =>
  lmsFetch<RegradeOut>(`${grades(courseId, assignmentId)}/regrade`, { method: "POST" });
