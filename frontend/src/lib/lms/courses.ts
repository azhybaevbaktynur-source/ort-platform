import { lmsFetch } from "./client";
import type {
  AddStaffIn, CourseCard, CourseCreateIn, CourseOut, CourseStaffOut, CourseUpdateIn, JoinCodeOut, JoinOut,
  Lang, MeOut, PageOut, RosterEntryOut, StaffPublicOut,
} from "./types";

const enc = encodeURIComponent;

export const getMe = () => lmsFetch<MeOut>("/me/lms");
export const patchMe = (locale: Lang) => lmsFetch<MeOut>("/me/lms", { method: "PATCH", body: { locale } });

export const listMyCourses = (as: "teaching" | "learning" | "all", cursor?: string | null, limit = 24) =>
  lmsFetch<PageOut<CourseCard>>("/courses", { params: { as, cursor, limit } });
export const listTrash = (cursor?: string | null, limit = 24) =>
  lmsFetch<PageOut<CourseCard>>("/courses/trash", { params: { cursor, limit } });

export const createCourse = (body: CourseCreateIn) => lmsFetch<CourseStaffOut>("/courses", { method: "POST", body });
// Phase 6b integration: an org admin reading a course of their organization has no enrollment
// (`my_enrollment: null`); they get the read-only student views (PHASE_6_DESIGN 2.2), so the pages see a
// student-like, id-less enrollment instead of null.
export const getCourse = async (id: string): Promise<CourseOut> => {
  const c = await lmsFetch<CourseOut>(`/courses/${enc(id)}`);
  if (!c.my_enrollment) {
    c.my_enrollment = { id: "", course_id: c.id, role: "student", state: "active", activated_at: null };
  }
  return c;
};
export const updateCourse = (id: string, body: CourseUpdateIn) =>
  lmsFetch<CourseStaffOut>(`/courses/${enc(id)}`, { method: "PATCH", body });

const transition = (id: string, action: string) =>
  lmsFetch<CourseStaffOut>(`/courses/${enc(id)}/${action}`, { method: "POST" });
export const publishCourse = (id: string) => transition(id, "publish");
export const unpublishCourse = (id: string) => transition(id, "unpublish");
export const concludeCourse = (id: string) => transition(id, "conclude");
export const reopenCourse = (id: string) => transition(id, "reopen");
export const restoreCourse = (id: string) => transition(id, "restore");
export const deleteCourse = (id: string) => lmsFetch<void>(`/courses/${enc(id)}`, { method: "DELETE" });

export const transferOwnership = (id: string, newOwnerUserId: string) =>
  lmsFetch<CourseStaffOut>(`/courses/${enc(id)}/transfer-ownership`, {
    method: "POST",
    body: { new_owner_user_id: newOwnerUserId },
  });
export const regenerateJoinCode = (id: string) =>
  lmsFetch<JoinCodeOut>(`/courses/${enc(id)}/join-code/regenerate`, { method: "POST" });
export const joinByCode = (code: string) => lmsFetch<JoinOut>("/courses/join", { method: "POST", body: { code } });
export const leaveCourse = (id: string) => lmsFetch<void>(`/courses/${enc(id)}/leave`, { method: "POST" });

export interface PeopleQuery {
  role?: string;
  state?: "active" | "removed";
  q?: string;
  cursor?: string | null;
  limit?: number;
}
/** Staff receive RosterEntryOut items, students receive StaffPublicOut items. */
export const listPeople = (id: string, query: PeopleQuery = {}) =>
  lmsFetch<PageOut<RosterEntryOut | StaffPublicOut>>(`/courses/${enc(id)}/people`, { params: { ...query } });

export const addStaff = (id: string, body: AddStaffIn) =>
  lmsFetch<RosterEntryOut>(`/courses/${enc(id)}/staff`, { method: "POST", body });
export const changeEnrollmentRole = (id: string, enrollmentId: string, role: string) =>
  lmsFetch<RosterEntryOut>(`/courses/${enc(id)}/enrollments/${enc(enrollmentId)}`, { method: "PATCH", body: { role } });
export const removeEnrollment = (id: string, enrollmentId: string) =>
  lmsFetch<void>(`/courses/${enc(id)}/enrollments/${enc(enrollmentId)}`, { method: "DELETE" });

/** Join code helpers (P1-1): uppercase, strip spaces and dashes. */
export function normalizeJoinCode(input: string): string {
  return input.toUpperCase().replace(/[\s-]/g, "");
}
export function formatJoinCode(code: string): string {
  const c = normalizeJoinCode(code);
  return c.length > 4 ? `${c.slice(0, 4)}-${c.slice(4, 8)}` : c;
}
