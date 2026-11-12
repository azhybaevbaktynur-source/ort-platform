import { lmsFetch } from "./client";
import type {
  AdminAttemptOut, AdminCatalogRowOut, AdminCourseOut, AdminUserDetailOut, AdminUserOut, AuditEntryOut, PageOut, PlatformSummaryOut,
  RosterEntryOut, TeacherRequestAdminOut, TeacherRequestStatus, TeacherRowOut, TeacherStatus,
} from "./types";

const enc = encodeURIComponent;
const post = <T,>(path: string, body?: unknown) => lmsFetch<T>(path, { method: "POST", body: body ?? {} });

export const getPlatformSummary = () => lmsFetch<PlatformSummaryOut>("/platform/summary");

/** FB8-5 S4: the overview page's numbers (`GET /platform/overview`, cached 60 s on the server; D-FB8-5-4). */
export interface PlatformOverviewOut {
  users_total: number;
  /** Distinct non-test people with a non-preview attempt started in the last 7 days. */
  active_students_7d: number;
  pro_active: number;
  /** Non-preview, non-practice attempts submitted in the last 7 days. */
  attempts_submitted_7d: number;
  pending_teacher_requests: number;
  /** Step 3b S1: courses waiting for a catalog decision. */
  catalog_pending?: number;
  /** Owner D10: courses that left the catalog in the last 7 days because their teacher was revoked. */
  catalog_revoked_7d?: number;
  storage_level: "ok" | "warn" | "full";
  reveals_last_hour: number;
  reveal_alert: boolean;
  /** DB_STORAGE_REVIEW 7.4: the stored database measurement (Services panel); null when it could not be read. */
  database?: PlatformOverviewDatabase | null;
  computed_at: string;
}
export interface PlatformOverviewDatabase {
  level: "ok" | "notice" | "warning" | "critical";
  percent: number | null;
  fits: number | null;
  used_bytes: number | null;
  limit_bytes: number | null;
  measured_at: string | null;
}
export const getPlatformOverview = () => lmsFetch<PlatformOverviewOut>("/platform/overview");

export const listTeacherRequests = (status: TeacherRequestStatus | "all", cursor?: string | null, limit = 25) =>
  lmsFetch<PageOut<TeacherRequestAdminOut>>("/platform/teacher-requests", { params: { status, cursor, limit } });
export const approveTeacherRequest = (id: string, note?: string) =>
  post<TeacherRequestAdminOut>(`/platform/teacher-requests/${enc(id)}/approve`, note ? { note } : {});
export const rejectTeacherRequest = (id: string, reason: string) =>
  post<TeacherRequestAdminOut>(`/platform/teacher-requests/${enc(id)}/reject`, { reason });

/** Step 3b S3: Admin → Преподаватели (`GET /platform/teachers`, by name, cursor-paged). */
export type TeacherListKind = "independent" | "school";
export type TeacherListStatus = "approved" | "revoked";
export const listTeachers = (p: { q?: string; kind?: TeacherListKind | ""; status?: TeacherListStatus | ""; cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<TeacherRowOut>>("/platform/teachers", { params: { limit: 25, ...p, kind: p.kind || undefined, status: p.status || undefined } });

export interface ListUsersParams {
  q?: string;
  teacher_status?: TeacherStatus | "";
  disabled?: boolean;
  /** S4 filters */
  email_unverified?: boolean;
  platform_admin?: boolean;
  has_access?: boolean;
  cursor?: string | null;
  limit?: number;
}
export const listUsers = (p: ListUsersParams) =>
  lmsFetch<PageOut<AdminUserOut>>("/platform/users", { params: { limit: 25, ...p } });
export const getUser = (id: string) => lmsFetch<AdminUserDetailOut>(`/platform/users/${enc(id)}`);
export const setTeacherStatus = (id: string, status: "approved" | "revoked", reason?: string) =>
  post<AdminUserOut>(`/platform/users/${enc(id)}/teacher-status`, reason ? { status, reason } : { status });
export const disableUser = (id: string, reason: string) =>
  post<AdminUserOut>(`/platform/users/${enc(id)}/disable`, { reason });
export const enableUser = (id: string) => post<AdminUserOut>(`/platform/users/${enc(id)}/enable`);

export interface ListAdminCoursesParams {
  q?: string;
  status?: string;
  deleted?: boolean;
  owner_id?: string;
  /** TEACHER_TO_STUDENT_MAP S3: only the live platform exam-prep courses (the exam-link select) */
  exam_prep?: boolean;
  cursor?: string | null;
  limit?: number;
}
export const listAdminCourses = (p: ListAdminCoursesParams) =>
  lmsFetch<PageOut<AdminCourseOut>>("/platform/courses", { params: { limit: 25, ...p } });
export const getAdminCourse = (id: string) => lmsFetch<AdminCourseOut>(`/platform/courses/${enc(id)}`);
export const adminCoursePeople = (id: string, cursor?: string | null, limit = 50) =>
  lmsFetch<PageOut<RosterEntryOut>>(`/platform/courses/${enc(id)}/people`, { params: { cursor, limit } });
export const adminDeleteCourse = (id: string, reason: string) =>
  post<AdminCourseOut>(`/platform/courses/${enc(id)}/delete`, { reason });
export const adminRestoreCourse = (id: string, reason: string) =>
  post<AdminCourseOut>(`/platform/courses/${enc(id)}/restore`, { reason });
export const unlistCourse = (id: string, reason?: string) =>
  post<AdminCourseOut>(`/platform/courses/${enc(id)}/unlist`, reason ? { reason } : {});
export const relistCourse = (id: string, reason?: string) =>
  post<AdminCourseOut>(`/platform/courses/${enc(id)}/relist`, reason ? { reason } : {});
/** Step 3b (CATALOG_AND_TEACHERS_DESIGN 2.4): Admin → Каталог, one listing state per page. */
export type AdminCatalogState = "pending" | "listed" | "declined" | "blocked";
export const listAdminCatalog = (state: AdminCatalogState, cursor?: string | null, limit = 25) =>
  lmsFetch<PageOut<AdminCatalogRowOut>>("/platform/catalog", { params: { state, cursor, limit } });
/** `pending` → `listed` (email to the owner); on a listed course the re-check that clears the content-changed marker. */
export const approveListing = (id: string, note?: string) =>
  post<AdminCourseOut>(`/platform/courses/${enc(id)}/listing/approve`, note ? { note } : {});
/** `pending` → `declined`; the note is required (course staff see it, students never). */
export const declineListing = (id: string, note: string) =>
  post<AdminCourseOut>(`/platform/courses/${enc(id)}/listing/decline`, { note });
export const adminTransferOwnership = (id: string, new_owner_user_id: string, reason: string) =>
  post<AdminCourseOut>(`/platform/courses/${enc(id)}/transfer-ownership`, { new_owner_user_id, reason });

export interface ListAuditParams {
  actor_id?: string;
  action?: string;
  target_type?: string;
  target_id?: string;
  /** Item 4: `details.acting_as` ("platform_admin": a platform admin acted inside an organization). */
  acting_as?: "org_admin" | "platform_admin" | "";
  cursor?: string | null;
  limit?: number;
}
export const listAuditLog = (p: ListAuditParams) =>
  lmsFetch<PageOut<AuditEntryOut>>("/platform/audit-log", { params: { limit: 50, ...p } });

// --- S4 person page ---
export const listUserAttempts = (id: string, cursor?: string | null, limit = 10) =>
  lmsFetch<PageOut<AdminAttemptOut>>(`/platform/users/${enc(id)}/attempts`, { params: { cursor, limit } });
export const sendPasswordReset = (id: string, reason: string) =>
  post<{ sent: boolean }>(`/platform/users/${enc(id)}/password-reset`, { reason });
export const adminChangeEmail = (id: string, newEmail: string, reason: string) =>
  post<AdminUserDetailOut>(`/platform/users/${enc(id)}/email-change`, { new_email: newEmail, reason });
export const adminCancelEmailChange = (id: string, reason: string) =>
  post<AdminUserDetailOut>(`/platform/users/${enc(id)}/email-change/cancel`, { reason });
/** The privacy function: correcting to under 14 starts the parent-consent grace period; correcting up grants nothing. */
export const correctAgeBand = (id: string, ageBand: string, reason: string) =>
  post<{ user_id: string; age_band: string; consent_state: string }>(`/admin/privacy/users/${enc(id)}/age-band`, { age_band: ageBand, reason });
