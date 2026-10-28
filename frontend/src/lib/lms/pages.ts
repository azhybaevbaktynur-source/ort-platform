// Phase 8a S4b: pages API client (design 7.2). Types in pagesTypes.ts.
import { lmsFetch } from "./client";
import type { PageOut } from "./types";
import type {
  PageAnyOut, PageCreateIn, PageStaffOut, PageSummaryStaffOut, PageSummaryStudentOut, PageUpdateIn,
} from "./pagesTypes";

const e = encodeURIComponent;
const base = (c: string) => `/courses/${e(c)}/pages`;

export const listPages = (courseId: string, q: { cursor?: string | null; limit?: number; deleted?: boolean } = {}) =>
  lmsFetch<PageOut<PageSummaryStaffOut | PageSummaryStudentOut>>(base(courseId), { params: { cursor: q.cursor, limit: q.limit, deleted: q.deleted } });
export const getPage = (courseId: string, pageId: string) => lmsFetch<PageAnyOut>(`${base(courseId)}/${e(pageId)}`);
export const createPage = (courseId: string, body: PageCreateIn) => lmsFetch<PageStaffOut>(base(courseId), { method: "POST", body });
export const updatePage = (courseId: string, pageId: string, body: PageUpdateIn) =>
  lmsFetch<PageStaffOut>(`${base(courseId)}/${e(pageId)}`, { method: "PATCH", body });
export const deletePage = (courseId: string, pageId: string) => lmsFetch<void>(`${base(courseId)}/${e(pageId)}`, { method: "DELETE" });
export const restorePage = (courseId: string, pageId: string) =>
  lmsFetch<PageStaffOut>(`${base(courseId)}/${e(pageId)}/restore`, { method: "POST" });
/** Server-side Markdown render (sanitized); never stored. */
export const previewMarkdown = (courseId: string, bodyMd: string, signal?: AbortSignal) =>
  lmsFetch<{ body_html: string }>(`${base(courseId)}/preview`, { method: "POST", body: { body_md: bodyMd }, signal });
