// Organizations API (docs/phases/PHASE_6_DESIGN.md §2.3): platform admin `/platform/organizations/*`,
// org admin `/org/{orgId}/*`, and `/me/organizations`. Snake_case DTOs like the rest of lib/lms.
import { lmsFetch } from "./client";
import type { CourseCreateIn, CourseStaffOut, CourseStatus, LocalizedText, PageOut, UserBrief } from "./types";

const enc = encodeURIComponent;
const post = <T,>(path: string, body?: unknown) => lmsFetch<T>(path, { method: "POST", body: body ?? {} });

export type OrgStatus = "active" | "suspended";
export type OrgRole = "org_admin" | "teacher";
export type OrgMemberState = "active" | "removed";

export interface OrgSettings {
  teachers_can_create_courses?: boolean;
  [k: string]: unknown;
}

export interface OrgCounts {
  org_admins?: number;
  teachers?: number;
  courses?: number;
  students?: number;
  pending_invitations?: number;
}

export interface OrganizationOut {
  id: string;
  slug: string;
  name: string;
  status: OrgStatus;
  parent_id: string | null;
  settings: OrgSettings;
  created_at: string;
  suspended_at: string | null;
  suspended_reason: string | null;
  counts: OrgCounts;
}

export interface OrgMemberOut {
  user_id: string;
  display_name: string | null;
  email: string;
  role: OrgRole;
  state: OrgMemberState;
  created_at: string;
  /** Assumed optional extras (shown when present). */
  course_count?: number;
  disabled?: boolean;
}

export interface OrgUsageOut {
  teachers: number;
  courses: number;
  students: number;
  banks: number;
  questions: number;
  storage_bytes: number;
}

export interface OrgTemplateGrantOut {
  template_key: string;
  title_key: string;
  granted: boolean;
  granted_at: string | null;
}

/** GET /platform/templates (registry listing). */
export interface PlatformTemplateOut {
  key: string;
  title_key: string;
  version?: number;
}

/** Course row of `/platform/organizations/{id}/courses` and `/org/{id}/courses` (assumed AdminCourseOut-like). */
export interface OrgCourseOut {
  id: string;
  title: LocalizedText;
  owner: UserBrief | null;
  status: CourseStatus;
  active_student_count?: number;
  template_key?: string | null;
  default_language?: string;
  created_at?: string;
  deleted_at?: string | null;
}

/** GET /org/{orgId} */
export interface OrgSummaryOut {
  id: string;
  name: string;
  slug: string;
  status: OrgStatus;
  settings: OrgSettings;
  counts: OrgCounts;
}

/** GET /me/organizations */
export interface MyOrganizationOut {
  id: string;
  name: string;
  slug: string;
  role: OrgRole;
  status: OrgStatus;
}

export interface OrganizationCreateIn {
  name: string;
  slug: string;
  contact_email?: string;
}
export interface OrganizationUpdateIn {
  name?: string;
  slug?: string;
  settings?: OrgSettings;
}

/** Accept a paginated `{items, next_cursor}` or a bare array (tolerant while the backend lands). */
export function asPage<T>(x: PageOut<T> | T[] | null | undefined): PageOut<T> {
  if (Array.isArray(x)) return { items: x, next_cursor: null };
  return { items: x?.items ?? [], next_cursor: x?.next_cursor ?? null };
}
const page = async <T,>(p: Promise<PageOut<T> | T[]>) => asPage(await p);

export interface ListParams {
  q?: string;
  cursor?: string | null;
  limit?: number;
}

// --- Platform admin ---

export const listOrganizations = (p: ListParams & { status?: OrgStatus | "" } = {}) =>
  page(lmsFetch<PageOut<OrganizationOut>>("/platform/organizations", { params: { limit: 25, ...p } }));
export const createOrganization = (body: OrganizationCreateIn) => post<OrganizationOut>("/platform/organizations", body);
export const getOrganization = (id: string) => lmsFetch<OrganizationOut>(`/platform/organizations/${enc(id)}`);
export const updateOrganization = (id: string, body: OrganizationUpdateIn) =>
  lmsFetch<OrganizationOut>(`/platform/organizations/${enc(id)}`, { method: "PATCH", body });
export const suspendOrganization = (id: string, reason: string) =>
  post<OrganizationOut>(`/platform/organizations/${enc(id)}/suspend`, { reason });
export const resumeOrganization = (id: string, reason: string) =>
  post<OrganizationOut>(`/platform/organizations/${enc(id)}/resume`, { reason });

export const listOrganizationMembers = (id: string, p: ListParams & { role?: OrgRole; state?: OrgMemberState } = {}) =>
  page(lmsFetch<PageOut<OrgMemberOut>>(`/platform/organizations/${enc(id)}/members`, { params: { limit: 50, ...p } }));
export const addOrganizationMember = (id: string, user_id: string, role: OrgRole) =>
  post<OrgMemberOut>(`/platform/organizations/${enc(id)}/members`, { user_id, role });
export const removeOrganizationMember = (id: string, userId: string, reason: string) =>
  lmsFetch<void>(`/platform/organizations/${enc(id)}/members/${enc(userId)}`, { method: "DELETE", body: { reason } });

export const listOrganizationCourses = (id: string, p: ListParams = {}) =>
  page(lmsFetch<PageOut<OrgCourseOut>>(`/platform/organizations/${enc(id)}/courses`, { params: { limit: 25, ...p } }));
export const getOrganizationUsage = (id: string) => lmsFetch<OrgUsageOut>(`/platform/organizations/${enc(id)}/usage`);
export const listOrganizationTemplates = (id: string) =>
  lmsFetch<OrgTemplateGrantOut[]>(`/platform/organizations/${enc(id)}/templates`);
export const grantTemplate = (id: string, key: string) =>
  lmsFetch<OrgTemplateGrantOut>(`/platform/organizations/${enc(id)}/templates/${enc(key)}`, { method: "PUT", body: {} });
export const revokeTemplate = (id: string, key: string) =>
  lmsFetch<void>(`/platform/organizations/${enc(id)}/templates/${enc(key)}`, { method: "DELETE" });
export const listPlatformTemplates = () => lmsFetch<PlatformTemplateOut[]>("/platform/templates");

// --- Org admin ---

export const getOrg = (orgId: string) => lmsFetch<OrgSummaryOut>(`/org/${enc(orgId)}`);
export const listOrgMembers = (orgId: string, p: ListParams & { role?: OrgRole; state?: OrgMemberState } = {}) =>
  page(lmsFetch<PageOut<OrgMemberOut>>(`/org/${enc(orgId)}/members`, { params: { limit: 50, ...p } }));
export const removeOrgMember = (orgId: string, userId: string, reason: string) =>
  lmsFetch<void>(`/org/${enc(orgId)}/members/${enc(userId)}`, { method: "DELETE", body: { reason } });
export const listOrgCourses = (orgId: string, p: ListParams = {}) =>
  page(lmsFetch<PageOut<OrgCourseOut>>(`/org/${enc(orgId)}/courses`, { params: { limit: 25, ...p } }));
/** POST /org/{orgId}/courses: the POST /courses body plus `owner_id`. */
export const createOrgCourse = (orgId: string, body: CourseCreateIn & { owner_id: string }) =>
  post<CourseStaffOut>(`/org/${enc(orgId)}/courses`, body);
export const joinCourseAsTeacher = (orgId: string, courseId: string) =>
  post<unknown>(`/org/${enc(orgId)}/courses/${enc(courseId)}/join-as-teacher`);

// --- Me ---

export const listMyOrganizations = () => lmsFetch<MyOrganizationOut[]>("/me/organizations");

// --- Helpers ---

/** System accounts (admin M5): the ORT demo teacher and any `@platform.invalid` address. Not editable. */
export const SYSTEM_USER_IDS = ["usr_ort_demo_teacher"];
export function isSystemAccount(u: { id?: string | null; user_id?: string | null; email?: string | null } | null | undefined): boolean {
  if (!u) return false;
  const id = u.id ?? u.user_id ?? "";
  return SYSTEM_USER_IDS.includes(id) || !!u.email?.toLowerCase().endsWith("@platform.invalid");
}

const TRANSLIT: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z", и: "i", й: "i", к: "k", л: "l", м: "m",
  н: "n", ң: "n", о: "o", ө: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ү: "u", ф: "f", х: "h", ц: "ts", ч: "ch",
  ш: "sh", щ: "sch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
};

/** Slug proposal from a name (`^[a-z0-9-]{2,64}$`), Cyrillic transliterated. */
export function slugify(name: string): string {
  const s = Array.from(name.toLowerCase()).map((c) => TRANSLIT[c] ?? c).join("");
  return s.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64).replace(/-+$/g, "");
}
export const SLUG_RE = /^[a-z0-9-]{2,64}$/;

export function formatBytes(n: number | null | undefined, locale?: string): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let v = n;
  let i = 0;
  while (v >= 1000 && i < units.length - 1) { v /= 1000; i += 1; }
  return `${v.toLocaleString(locale, { maximumFractionDigits: i === 0 ? 0 : 1 })} ${units[i]}`;
}
