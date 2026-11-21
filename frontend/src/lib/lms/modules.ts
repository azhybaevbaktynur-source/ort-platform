// Phase 8a S4a: modules API client (docs/phases/PHASE_8A_DESIGN.md 7.1). Types in modulesTypes.ts.
// The add-item pickers read the pages and course-files lists through the small helpers at the end (minimal shapes);
// file downloads reuse `downloadCourseFile` of courseFiles.ts (S4b).
import { getAuthHeader } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";
import { LmsApiError, lmsFetch } from "./client";
import { toError } from "./courseFiles";
import type { AssignmentCreateIn } from "./assignmentTypes";
import type { PageOut } from "./types";
import type {
  CourseFilePickOut, CourseVideoOut, VideoPlayOut, ItemIn, ItemStaffOut, ItemUpdateIn, ModuleIn, ModulesOut, ModuleStaffOut, ModuleStudentOut,
  ModulesStudentOut, ModuleUpdateIn, PagePickOut, QuizItemOut, ReapplyOut, RequirementIn,
} from "./modulesTypes";

const e = encodeURIComponent;
const course = (c: string) => `/courses/${e(c)}`;
const mods = (c: string) => `${course(c)}/modules`;
const mod = (c: string, m: string) => `${mods(c)}/${e(m)}`;
const item = (c: string, m: string, i: string) => `${mod(c, m)}/items/${e(i)}`;

// ---- outline ----
export const getModules = (courseId: string, opts: { deleted?: boolean; signal?: AbortSignal } = {}) =>
  lmsFetch<ModulesOut>(mods(courseId), { params: { deleted: opts.deleted || undefined }, signal: opts.signal });
export const createModule = (courseId: string, body: ModuleIn) =>
  lmsFetch<ModuleStaffOut>(mods(courseId), { method: "POST", body });
export const updateModule = (courseId: string, moduleId: string, body: ModuleUpdateIn) =>
  lmsFetch<ModuleStaffOut>(mod(courseId, moduleId), { method: "PATCH", body });
export const deleteModule = (courseId: string, moduleId: string) =>
  lmsFetch<void>(mod(courseId, moduleId), { method: "DELETE" });
export const restoreModule = (courseId: string, moduleId: string) =>
  lmsFetch<ModuleStaffOut>(`${mod(courseId, moduleId)}/restore`, { method: "POST" });
export const reorderModules = (courseId: string, ids: string[]) =>
  lmsFetch<unknown>(`${mods(courseId)}/order`, { method: "PUT", body: { ids } });
export const setPrerequisites = (courseId: string, moduleId: string, moduleIds: string[]) =>
  lmsFetch<ModuleStaffOut>(`${mod(courseId, moduleId)}/prerequisites`, { method: "PUT", body: { module_ids: moduleIds } });

// ---- items ----
export const addItem = (courseId: string, moduleId: string, body: ItemIn) =>
  lmsFetch<ItemStaffOut>(`${mod(courseId, moduleId)}/items`, { method: "POST", body });
export const updateItem = (courseId: string, moduleId: string, itemId: string, body: ItemUpdateIn) =>
  lmsFetch<ItemStaffOut>(item(courseId, moduleId, itemId), { method: "PATCH", body });
export const deleteItem = (courseId: string, moduleId: string, itemId: string) =>
  lmsFetch<void>(item(courseId, moduleId, itemId), { method: "DELETE" });
export const reorderItems = (courseId: string, moduleId: string, ids: string[]) =>
  lmsFetch<unknown>(`${mod(courseId, moduleId)}/items/order`, { method: "PUT", body: { ids } });
export const moveItem = (courseId: string, moduleId: string, itemId: string, toModuleId: string, position: number) =>
  lmsFetch<unknown>(`${item(courseId, moduleId, itemId)}/move`, { method: "PUT", body: { module_id: toModuleId, position } });
export const setRequirement = (courseId: string, moduleId: string, itemId: string, body: RequirementIn) =>
  lmsFetch<unknown>(`${item(courseId, moduleId, itemId)}/requirement`, { method: "PUT", body });
export const clearRequirement = (courseId: string, moduleId: string, itemId: string) =>
  lmsFetch<void>(`${item(courseId, moduleId, itemId)}/requirement`, { method: "DELETE" });

/** "New quiz" from a module: the 7a quiz assignment and its item in one transaction; open `/assessments/{id}/edit`. */
export const createQuizItem = (courseId: string, moduleId: string, body: AssignmentCreateIn) =>
  lmsFetch<QuizItemOut>(`${mod(courseId, moduleId)}/quiz`, { method: "POST", body });

export const reapplyCourse = (courseId: string) =>
  lmsFetch<ReapplyOut>(`${mods(courseId)}/reapply`, { method: "POST" });
export const reapplyModule = (courseId: string, moduleId: string) =>
  lmsFetch<ReapplyOut>(`${mod(courseId, moduleId)}/reapply`, { method: "POST" });

// ---- student facts (return the module state, so the view updates without a second call) ----
export const recordView = (courseId: string, moduleId: string, itemId: string) =>
  lmsFetch<ModuleStudentOut>(`${item(courseId, moduleId, itemId)}/view`, { method: "POST", body: {} });
export const setDone = (courseId: string, moduleId: string, itemId: string, done: boolean) =>
  lmsFetch<ModuleStudentOut>(`${item(courseId, moduleId, itemId)}/done`, { method: "POST", body: { done } });

/** One student's modules (teacher progress drawer). */
export const getStudentProgress = (courseId: string, enrollmentId: string) =>
  lmsFetch<ModulesStudentOut>(`${mods(courseId)}/progress/${e(enrollmentId)}`);

// ---- picker helpers over the pages / course-files lists ----
export const listPagesForPicker = (courseId: string, cursor?: string | null) =>
  lmsFetch<PageOut<PagePickOut>>(`${course(courseId)}/pages`, { params: { cursor, limit: 50 } });
export const listCourseFilesForPicker = (courseId: string, cursor?: string | null) =>
  lmsFetch<PageOut<CourseFilePickOut>>(`${course(courseId)}/course-files`, { params: { cursor, limit: 50 } });

// ---- LESSON_VIDEOS V2, V3: hosted lesson videos ----
/** Staff: upload an MP4 (multipart `file` + optional `title`) with progress 0..1 (XMLHttpRequest); 201 new, 200 the same
 * file already in the course. Errors: `video_invalid`, `payload_too_large`, `storage_full`. */
export async function uploadCourseVideo(
  courseId: string,
  input: { file: File; title?: string },
  onProgress?: (ratio: number) => void,
  signal?: AbortSignal,
): Promise<CourseVideoOut> {
  const headers = await getAuthHeader();
  return new Promise<CourseVideoOut>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}${course(courseId)}/videos`);
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (ev) => { if (ev.lengthComputable && onProgress) onProgress(ev.loaded / ev.total); };
    xhr.onerror = () => reject(new LmsApiError(0, "network", "Network error"));
    xhr.onabort = () => reject(new DOMException("Aborted", "AbortError"));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText) as CourseVideoOut); } catch { reject(new LmsApiError(500, "unknown", "Bad response")); }
      } else reject(toError(xhr.status, xhr.responseText));
    };
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    const form = new FormData();
    form.append("file", input.file);
    if (input.title) form.append("title", input.title);
    xhr.send(form);
  });
}

/** A video item's short-lived address (student, staff, Student view); 403 `item_locked`, 404 for outsiders. */
export const getItemPlay = (courseId: string, moduleId: string, itemId: string, signal?: AbortSignal) =>
  lmsFetch<VideoPlayOut>(`${item(courseId, moduleId, itemId)}/play`, { signal });
