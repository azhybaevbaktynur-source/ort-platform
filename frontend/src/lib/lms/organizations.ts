// Organizations API (docs/phases/PHASE_6_DESIGN.md §2.3): platform admin `/platform/organizations/*`,
// org admin `/org/{orgId}/*`, and `/me/organizations`. Snake_case DTOs like the rest of lib/lms.
import { lmsFetch } from "./client";
import type {
  CourseCreateIn, CourseStatus, DepartmentOut as DepartmentBaseOut, LocalizedText, OrganizationSettings,
  OrganizationSettingsIn, OrganizationTreeFields, OrgKind, PageOut, RosterEntryOut, SharedBankRowOut, UserBrief,
} from "./types";
import type { BankOut, PassageSummaryOut, QuestionStaffOut } from "./contentTypes";

const enc = encodeURIComponent;
const post = <T,>(path: string, body?: unknown) => lmsFetch<T>(path, { method: "POST", body: body ?? {} });

export type OrgStatus = "active" | "suspended";
export type OrgRole = "org_admin" | "teacher";
export type OrgMemberState = "active" | "removed";

export interface OrgSettings {
  teachers_can_create_courses?: boolean;
  [k: string]: unknown;
}

/** `OrganizationOut` (POST/PATCH/suspend/resume of /platform/organizations). Phase 9: + tree fields. */
export interface OrganizationOut extends OrganizationTreeFields {
  id: string;
  slug: string;
  name: string;
  status: OrgStatus;
  parent_id: string | null;
  settings: OrgSettings;
  created_at: string;
  suspended_at: string | null;
  suspended_reason: string | null;
}

/** `OrganizationAdminRowOut`: GET /platform/organizations (rows) and GET /platform/organizations/{id}. */
export interface OrganizationAdminRowOut extends OrganizationOut {
  org_admins: number;
  teachers: number;
  courses: number;
}

/** `MemberOut` of the members lists and of POST .../members. */
export interface OrgMemberOut {
  user: UserBrief;
  role: OrgRole;
  state: OrgMemberState;
  created_at: string;
  removed_at: string | null;
}

/** `UsageOut`: GET /platform/organizations/{id}/usage and `usage` of GET /org/{id}. */
export interface OrgUsageOut {
  organization_id: string;
  org_admins: number;
  teachers: number;
  courses: number;
  students: number;
  banks: number;
  questions: number;
  storage_bytes: number;
}

/** `OrgTemplateOut`: GET /platform/organizations/{id}/templates (every known template, granted or not). */
export interface OrgTemplateGrantOut {
  key: string;
  version: number;
  granted: boolean;
  granted_at: string | null;
  revoked_at: string | null;
}

/** GET /platform/templates (registry listing). The backend sends no title; use `templateTitle(t, key)`. */
export interface PlatformTemplateOut {
  key: string;
  version: number;
  title_key?: string | null;
}

/** `OrgCourseOut`: course rows of `/platform/organizations/{id}/courses`, `/org/{id}/courses` and POST /org/{id}/courses. */
export interface OrgCourseOut {
  id: string;
  title: LocalizedText;
  owner: UserBrief;
  status: CourseStatus;
  visibility: string;
  template_key: string | null;
  active_student_count: number;
  created_at: string;
  /** Phase 9 S2: the organization (department) the course belongs to. */
  organization_id?: string | null;
}

/** GET /org/{orgId}: the organization, its usage counts and my role (null for the platform admin). */
export interface OrgSummaryOut extends OrganizationOut {
  usage: OrgUsageOut;
  my_role: OrgRole | null;
}

/** GET /me/organizations item. */
export interface MyOrganizationOut {
  id: string;
  name: string;
  slug: string;
  role: OrgRole;
  status: OrgStatus;
  can_create_courses: boolean;
}

/** GET /platform/users/{userId}/organizations item (admin user detail). */
export interface UserOrganizationOut {
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  organization_status: OrgStatus;
  role: OrgRole;
  state: OrgMemberState;
  created_at: string;
  removed_at: string | null;
}

export interface OrganizationCreateIn {
  name: string;
  slug: string;
  settings?: { teachers_can_create_courses?: boolean };
}
export interface OrganizationUpdateIn {
  name?: string;
  slug?: string;
  settings?: OrganizationSettingsIn;
}

/** Normalize a `{items, next_cursor}` page (every Phase 6 list is cursor-paginated). */
export function asPage<T>(x: PageOut<T> | null | undefined): PageOut<T> {
  return { items: x?.items ?? [], next_cursor: x?.next_cursor ?? null };
}
const page = async <T,>(p: Promise<PageOut<T>>) => asPage(await p);

export interface ListParams {
  cursor?: string | null;
  limit?: number;
}

// --- Platform admin ---

export const listOrganizations = (p: ListParams & { q?: string; status?: OrgStatus | "" } = {}) =>
  page(lmsFetch<PageOut<OrganizationAdminRowOut>>("/platform/organizations", { params: { limit: 25, ...p } }));
export const createOrganization = (body: OrganizationCreateIn) => post<OrganizationOut>("/platform/organizations", body);
export const getOrganization = (id: string) => lmsFetch<OrganizationAdminRowOut>(`/platform/organizations/${enc(id)}`);
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
/** DELETE with the optional reason as a query parameter (the backend reads no body). */
export const removeOrganizationMember = (id: string, userId: string, reason: string) =>
  lmsFetch<void>(`/platform/organizations/${enc(id)}/members/${enc(userId)}`, { method: "DELETE", params: { reason } });

export const listOrganizationCourses = (id: string, p: ListParams & { deleted?: boolean } = {}) =>
  page(lmsFetch<PageOut<OrgCourseOut>>(`/platform/organizations/${enc(id)}/courses`, { params: { limit: 25, ...p } }));
export const getOrganizationUsage = (id: string) => lmsFetch<OrgUsageOut>(`/platform/organizations/${enc(id)}/usage`);
export const listOrganizationTemplates = (id: string) =>
  lmsFetch<OrgTemplateGrantOut[]>(`/platform/organizations/${enc(id)}/templates`);
export const grantTemplate = (id: string, key: string) =>
  lmsFetch<OrgTemplateGrantOut>(`/platform/organizations/${enc(id)}/templates/${enc(key)}`, { method: "PUT" });
/** Phase 6 S8: optional reason as a query parameter (audited), like removeOrganizationMember. */
export const revokeTemplate = (id: string, key: string, reason = "") =>
  lmsFetch<void>(`/platform/organizations/${enc(id)}/templates/${enc(key)}`, { method: "DELETE", params: { reason } });
export const listPlatformTemplates = () => lmsFetch<PlatformTemplateOut[]>("/platform/templates");
export const listUserOrganizations = (userId: string, p: ListParams & { state?: OrgMemberState } = {}) =>
  page(lmsFetch<PageOut<UserOrganizationOut>>(`/platform/users/${enc(userId)}/organizations`, { params: { limit: 50, ...p } }));

// --- Org admin (non-admins get 404 organization_not_found) ---

export const getOrg = (orgId: string) => lmsFetch<OrgSummaryOut>(`/org/${enc(orgId)}`);
export const listOrgMembers = (orgId: string, p: ListParams & { role?: OrgRole; state?: OrgMemberState } = {}) =>
  page(lmsFetch<PageOut<OrgMemberOut>>(`/org/${enc(orgId)}/members`, { params: { limit: 50, ...p } }));
export const removeOrgMember = (orgId: string, userId: string, reason: string) =>
  lmsFetch<void>(`/org/${enc(orgId)}/members/${enc(userId)}`, { method: "DELETE", params: { reason } });
export const listOrgCourses = (orgId: string, p: ListParams = {}) =>
  page(lmsFetch<PageOut<OrgCourseOut>>(`/org/${enc(orgId)}/courses`, { params: { limit: 25, ...p } }));
/** POST /org/{orgId}/courses: the POST /courses body plus `owner_id`; answers the course row. */
export const createOrgCourse = (orgId: string, body: CourseCreateIn & { owner_id: string }) =>
  post<OrgCourseOut>(`/org/${enc(orgId)}/courses`, body);
export const joinCourseAsTeacher = (orgId: string, courseId: string) =>
  post<RosterEntryOut>(`/org/${enc(orgId)}/courses/${enc(courseId)}/join-as-teacher`);

/** Name/email match of a member row (the members endpoints have no `q` filter: search the loaded rows). */
export function memberMatches(m: OrgMemberOut, q: string): boolean {
  const n = q.trim().toLowerCase();
  if (!n) return true;
  return (m.user.display_name ?? "").toLowerCase().includes(n) || m.user.email.toLowerCase().includes(n);
}

/** Picker search over the active members of an organization (first 100 members, filtered on the client). */
export async function searchOrgMembers(orgId: string, q: string, role?: OrgRole): Promise<UserBrief[]> {
  const page = await listOrgMembers(orgId, { state: "active", role, limit: 100 });
  return page.items.filter((m) => memberMatches(m, q) && !isSystemAccount(m.user)).slice(0, 10).map((m) => m.user);
}

// --- Phase 9 S2 begin --- (docs/phases/PHASE_9_DESIGN.md §4.1-4.3, §5: departments, settings, usage, shared banks)

/** A node of `GET /org/{orgId}/departments` (subtree, depth-first, the organization itself first). */
export interface DepartmentOut extends DepartmentBaseOut {
  status: OrgStatus;
  suspended_reason: string | null;
}
export interface DepartmentCreateIn {
  name: string;
  slug: string;
  parent_id?: string | null;
}
export interface DepartmentUpdateIn {
  name?: string;
  parent_id?: string;
}

/** `GET /org/{orgId}/settings`: effective settings of the tree; `editable` only on the root that stores them. */
export interface OrgSettingsViewOut {
  organization_id: string;
  root_id: string;
  root_name: string;
  kind: OrgKind;
  editable: boolean;
  settings: OrganizationSettings;
}

export interface DepartmentUsageOut {
  id: string;
  name: string;
  courses: number;
  teachers: number;
  students: number;
}
/** `GET /org/{orgId}/usage`: the subtree roll-up. */
export interface TreeUsageOut extends OrgUsageOut {
  by_department: DepartmentUsageOut[];
  course_files_bytes: number;
}

/** `GET /courses/{courseId}/bank-sharing`: may this course's banks be shared, and may the caller copy into it. */
export interface BankSharingOut {
  enabled: boolean;
  reason: "template_locked" | "personal" | "setting_off" | null;
  root_id: string;
  root_name: string;
  can_copy: boolean;
}

export const getOrgSettings = (orgId: string) => lmsFetch<OrgSettingsViewOut>(`/org/${enc(orgId)}/settings`);
export const updateOrgSettings = (orgId: string, body: OrganizationSettingsIn) =>
  lmsFetch<OrgSettingsViewOut>(`/org/${enc(orgId)}/settings`, { method: "PATCH", body });
export const getOrgUsage = (orgId: string) => lmsFetch<TreeUsageOut>(`/org/${enc(orgId)}/usage`);
export const listDepartments = (orgId: string) => lmsFetch<DepartmentOut[]>(`/org/${enc(orgId)}/departments`);
export const createDepartment = (orgId: string, body: DepartmentCreateIn) =>
  post<DepartmentOut>(`/org/${enc(orgId)}/departments`, body);
export const updateDepartment = (orgId: string, deptId: string, body: DepartmentUpdateIn) =>
  lmsFetch<DepartmentOut>(`/org/${enc(orgId)}/departments/${enc(deptId)}`, { method: "PATCH", body });
export const deleteDepartment = (orgId: string, deptId: string) =>
  lmsFetch<void>(`/org/${enc(orgId)}/departments/${enc(deptId)}`, { method: "DELETE" });
export const moveOrgCourse = (orgId: string, courseId: string, organizationId: string) =>
  lmsFetch<OrgCourseOut>(`/org/${enc(orgId)}/courses/${enc(courseId)}`, { method: "PATCH", body: { organization_id: organizationId } });
export const listPlatformDepartments = (orgId: string) =>
  lmsFetch<DepartmentOut[]>(`/platform/organizations/${enc(orgId)}/departments`);

export const listSharedBanks = (orgId: string, p: ListParams & { q?: string } = {}) =>
  page(lmsFetch<PageOut<SharedBankRowOut>>(`/org/${enc(orgId)}/shared-banks`, { params: { limit: 25, ...p } }));
export const getSharedBank = (orgId: string, bankId: string) =>
  lmsFetch<SharedBankRowOut>(`/org/${enc(orgId)}/shared-banks/${enc(bankId)}`);
export const listSharedBankQuestions = (orgId: string, bankId: string, p: ListParams & { q?: string } = {}) =>
  page(lmsFetch<PageOut<QuestionStaffOut>>(`/org/${enc(orgId)}/shared-banks/${enc(bankId)}/questions`, { params: { limit: 25, ...p } }));
export const listSharedBankPassages = (orgId: string, bankId: string, p: ListParams = {}) =>
  page(lmsFetch<PageOut<PassageSummaryOut>>(`/org/${enc(orgId)}/shared-banks/${enc(bankId)}/passages`, { params: { limit: 25, ...p } }));

export const getBankSharing = (courseId: string) => lmsFetch<BankSharingOut>(`/courses/${enc(courseId)}/bank-sharing`);
export const shareBank = (courseId: string, bankId: string) =>
  post<BankOut>(`/courses/${enc(courseId)}/banks/${enc(bankId)}/share`);
export const unshareBank = (courseId: string, bankId: string) =>
  lmsFetch<BankOut>(`/courses/${enc(courseId)}/banks/${enc(bankId)}/share`, { method: "DELETE" });
export const copySharedBank = (courseId: string, bankId: string) =>
  post<BankOut>(`/courses/${enc(courseId)}/banks/copy-from`, { bank_id: bankId });
// --- Phase 9 S2 end ---

// --- Me ---

export const listMyOrganizations = (p: ListParams = {}) =>
  page(lmsFetch<PageOut<MyOrganizationOut>>("/me/organizations", { params: { limit: 100, ...p } })).then((x) => x.items);

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
