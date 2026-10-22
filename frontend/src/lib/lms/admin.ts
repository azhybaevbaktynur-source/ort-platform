import { lmsFetch } from "./client";
import type {
  AdminCourseOut, AdminUserDetailOut, AdminUserOut, AuditEntryOut, PageOut, PlatformSummaryOut,
  RosterEntryOut, TeacherRequestAdminOut, TeacherRequestStatus, TeacherStatus,
} from "./types";

const enc = encodeURIComponent;
const post = <T,>(path: string, body?: unknown) => lmsFetch<T>(path, { method: "POST", body: body ?? {} });

export const getPlatformSummary = () => lmsFetch<PlatformSummaryOut>("/platform/summary");

export const listTeacherRequests = (status: TeacherRequestStatus | "all", cursor?: string | null, limit = 25) =>
  lmsFetch<PageOut<TeacherRequestAdminOut>>("/platform/teacher-requests", { params: { status, cursor, limit } });
export const approveTeacherRequest = (id: string, note?: string) =>
  post<TeacherRequestAdminOut>(`/platform/teacher-requests/${enc(id)}/approve`, note ? { note } : {});
export const rejectTeacherRequest = (id: string, reason: string) =>
  post<TeacherRequestAdminOut>(`/platform/teacher-requests/${enc(id)}/reject`, { reason });

export interface ListUsersParams {
  q?: string;
  teacher_status?: TeacherStatus | "";
  disabled?: boolean;
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
export const adminTransferOwnership = (id: string, new_owner_user_id: string, reason: string) =>
  post<AdminCourseOut>(`/platform/courses/${enc(id)}/transfer-ownership`, { new_owner_user_id, reason });

export interface ListAuditParams {
  actor_id?: string;
  action?: string;
  target_type?: string;
  target_id?: string;
  cursor?: string | null;
  limit?: number;
}
export const listAuditLog = (p: ListAuditParams) =>
  lmsFetch<PageOut<AuditEntryOut>>("/platform/audit-log", { params: { limit: 50, ...p } });
