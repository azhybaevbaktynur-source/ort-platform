// Phase 8a S4b: pages, course files and announcements API shapes (PHASE_8A_DESIGN 7.2; backend schemas.py of each package).
import type { Lang } from "./types";

export interface PageVariantOut { id: string; language: string; title: string }

export interface PageSummaryStaffOut {
  id: string; translation_group_id: string; language: string; title: string; published: boolean; rev: number;
  used_in_modules: number; created_at: string; updated_at: string; deleted_at?: string | null;
}
export interface PageSummaryStudentOut { id: string; translation_group_id: string; language: string; title: string }

export interface PageStaffOut {
  id: string; course_id: string; translation_group_id: string; language: string; title: string; body_md: string;
  body_html: string; published: boolean; rev: number; variants: PageVariantOut[]; created_at: string; updated_at: string;
  deleted_at?: string | null;
}
export interface PageStudentOut {
  id: string; translation_group_id: string; language: string; title: string; body_html: string;
  variants: PageVariantOut[]; updated_at: string;
}
/** `GET pages/{id}`: staff get the source and `rev`, students the render only. */
export type PageAnyOut = PageStaffOut | PageStudentOut;
export function isStaffPage(p: PageAnyOut): p is PageStaffOut { return "body_md" in p; }

export interface PageCreateIn {
  title: string; language: Lang; body_md?: string; published?: boolean; translation_group_id?: string | null;
}
export interface PageUpdateIn { rev: number; title?: string; body_md?: string; published?: boolean }

export interface CourseFileStaffOut {
  id: string; course_id: string; folder: string; title: string; published: boolean; bytes: number; mime: string;
  filename?: string | null; used_in_modules: number; created_at: string; updated_at: string; deleted_at?: string | null;
}
export interface CourseFileStudentOut { id: string; folder: string; title: string; bytes: number; created_at: string }
export interface CourseFilesQuotaOut { used: number; max: number }
export interface CourseFilesPageOut {
  items: Array<CourseFileStaffOut | CourseFileStudentOut>;
  next_cursor: string | null;
  quota?: CourseFilesQuotaOut | null;
}
export interface CourseFileUpdateIn { title?: string; folder?: string; published?: boolean }
export interface DownloadOut { url: string; expires_at?: string | null }

export interface AnnouncementStaffOut {
  id: string; course_id: string; title: string; body_md: string; body_html: string; pinned: boolean;
  published_at: string | null; rev: number; author_name: string; created_at: string; updated_at: string;
}
export interface AnnouncementStudentOut {
  id: string; title: string; body_html: string; pinned: boolean; published_at: string; author_name: string;
}
export interface AnnouncementCreateIn { title: string; body_md?: string; pinned?: boolean; publish?: boolean }
export interface AnnouncementUpdateIn { rev: number; title?: string; body_md?: string; pinned?: boolean }

/** `details.reasons[]` of 423 `module_locked` (design 6.5). */
export interface LockReason {
  kind: "unlock_at" | "prerequisite" | "sequential";
  at?: string | null; module_id?: string | null; item_id?: string | null; title?: Record<string, string> | null;
}
export interface ModuleLockedDetails {
  module_id?: string; module_title?: Record<string, string>; reasons?: LockReason[]; lock_reasons?: LockReason[];
}

export const FILE_MAX_BYTES = 10 * 1024 * 1024;
export const PAGE_BODY_MAX = 100_000;
export const ANNOUNCEMENT_BODY_MAX = 20_000;
