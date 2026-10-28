// Phase 8a S4b: announcements API client (design 7.2). Types in pagesTypes.ts.
import { lmsFetch } from "./client";
import type { PageOut } from "./types";
import type { AnnouncementCreateIn, AnnouncementStaffOut, AnnouncementStudentOut, AnnouncementUpdateIn } from "./pagesTypes";

const e = encodeURIComponent;
const base = (c: string) => `/courses/${e(c)}/announcements`;

export const listAnnouncements = (courseId: string, q: { cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<AnnouncementStaffOut | AnnouncementStudentOut>>(base(courseId), { params: { cursor: q.cursor, limit: q.limit } });
export const createAnnouncement = (courseId: string, body: AnnouncementCreateIn) =>
  lmsFetch<AnnouncementStaffOut>(base(courseId), { method: "POST", body });
export const updateAnnouncement = (courseId: string, id: string, body: AnnouncementUpdateIn) =>
  lmsFetch<AnnouncementStaffOut>(`${base(courseId)}/${e(id)}`, { method: "PATCH", body });
export const publishAnnouncement = (courseId: string, id: string) =>
  lmsFetch<AnnouncementStaffOut>(`${base(courseId)}/${e(id)}/publish`, { method: "POST" });
export const deleteAnnouncement = (courseId: string, id: string) => lmsFetch<void>(`${base(courseId)}/${e(id)}`, { method: "DELETE" });
