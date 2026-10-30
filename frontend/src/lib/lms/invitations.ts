// Invitations API (docs/phases/PHASE_6_DESIGN.md §2.3, §7).
import { getAuthHeader } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";
import { LmsApiError, lmsFetch } from "./client";
import { asPage, type ListParams } from "./organizations";
import type { Lang, LocalizedText, PageOut, RosterCounts, RosterImportOut, RosterKind } from "./types";

const enc = encodeURIComponent;
const post = <T,>(path: string, body?: unknown) => lmsFetch<T>(path, { method: "POST", body: body ?? {} });

export type InvitationRole = "org_admin" | "teacher" | "assistant" | "student"; // student: Phase 9 S3
export type InvitationState = "pending" | "accepted" | "revoked" | "expired";

/** `InvitationOut` of GET /org/{orgId}/invitations and of revoke. */
export interface InvitationOut {
  id: string;
  email: string;
  role: InvitationRole;
  course_id: string | null;
  /** Localized course title (staff invitations only). */
  course_title: LocalizedText | null;
  state: InvitationState;
  invited_by_name: string;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
}

/** `InvitationCreatedOut`: create, resend and course staff invitations. */
export interface InvitationCreatedOut extends InvitationOut {
  email_sent: boolean;
}

export interface OrgInvitationIn {
  email: string;
  role: "teacher" | "org_admin";
  message?: string;
  language: Lang;
}

/** GET /invitations/{token} (public). 404 = unknown, expired or revoked. */
export interface InvitationPublicOut {
  organization_name: string;
  role: InvitationRole;
  course_title: LocalizedText | null;
  masked_email: string;
  expires_at: string;
}

/** POST /invitations/{tokenOrId}/accept. */
export interface InvitationAcceptOut {
  organization_id: string;
  organization_name: string;
  role: InvitationRole;
  course_id: string | null;
  already_accepted: boolean;
}

/** GET /me/invitations item: pending invitations for my email. `id` works in place of the token in accept. */
export interface MyInvitationOut {
  id: string;
  organization_id: string;
  organization_name: string;
  role: InvitationRole;
  course_id: string | null;
  course_title: LocalizedText | null;
  invited_by_name: string;
  expires_at: string;
}

export const listOrgInvitations = (orgId: string, p: ListParams & { state?: InvitationState } = {}) =>
  lmsFetch<PageOut<InvitationOut>>(`/org/${enc(orgId)}/invitations`, { params: { limit: 50, ...p } }).then((x) => asPage<InvitationOut>(x));
export const createOrgInvitation = (orgId: string, body: OrgInvitationIn) =>
  post<InvitationCreatedOut>(`/org/${enc(orgId)}/invitations`, body);
export const revokeOrgInvitation = (orgId: string, id: string) =>
  post<InvitationOut>(`/org/${enc(orgId)}/invitations/${enc(id)}/revoke`);
export const resendOrgInvitation = (orgId: string, id: string) =>
  post<InvitationCreatedOut>(`/org/${enc(orgId)}/invitations/${enc(id)}/resend`);

export const getInvitation = (token: string) => lmsFetch<InvitationPublicOut>(`/invitations/${enc(token)}`);
/** Accept by the emailed token, or by the invitation id from GET /me/invitations (same route). */
export const acceptInvitation = (tokenOrId: string) => post<InvitationAcceptOut>(`/invitations/${enc(tokenOrId)}/accept`);
export const listMyInvitations = (p: ListParams = {}) =>
  lmsFetch<PageOut<MyInvitationOut>>("/me/invitations", { params: { limit: 50, ...p } }).then((x) => asPage<MyInvitationOut>(x).items);

/** Course owner (or a course manager, for assistants) invites a co-teacher or assistant who has no account yet. */
export const createCourseStaffInvitation = (courseId: string, body: { email: string; role: "teacher" | "assistant"; language: Lang }) =>
  post<InvitationCreatedOut>(`/courses/${enc(courseId)}/staff/invitations`, body);

/** Where to go after accepting: the course for a staff invitation, the org area for an org admin, else my courses. */
export function invitationTarget(lang: string, r: Pick<InvitationAcceptOut, "course_id" | "role" | "organization_id">): string {
  if (r.course_id) return `/${lang}/courses/${r.course_id}`;
  if (r.role === "org_admin") return `/${lang}/org/${r.organization_id}`;
  return `/${lang}/courses`;
}

/** Window event fired after an invitation was accepted, so the pending-invitations banner reloads. */
export const INVITATIONS_CHANGED_EVENT = "lms-invitations-changed";

// --- Phase 6 S8 (UX S1): one-time "You joined ..." notice on the page the accept redirects to ---
const ACCEPTED_KEY = "lms-invitation-accepted";

export interface AcceptedNoticeData {
  path: string;
  role: InvitationRole;
  org: string;
  course: string | null;
}

/** Remember the accepted invitation for the target page (sessionStorage; silently skipped when unavailable). */
export function rememberAccepted(path: string, r: Pick<InvitationAcceptOut, "role" | "organization_name" | "course_id">,
  courseTitle: string | null): void {
  const data: AcceptedNoticeData = { path, role: r.role, org: r.organization_name, course: r.course_id ? courseTitle : null };
  try { window.sessionStorage.setItem(ACCEPTED_KEY, JSON.stringify(data)); } catch { /* storage blocked */ }
}

/** Read and clear the remembered notice when it belongs to `pathname` (shown once). */
export function takeAccepted(pathname: string): AcceptedNoticeData | null {
  try {
    const raw = window.sessionStorage.getItem(ACCEPTED_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as AcceptedNoticeData;
    if (data.path !== pathname) return null;
    window.sessionStorage.removeItem(ACCEPTED_KEY);
    return data;
  } catch {
    return null;
  }
}

// --- Phase 9 S3 begin --- (PHASE_9_DESIGN 4.4, 4.5: student invitations and roster CSV imports)

/** Most addresses per "Invite students" request (the server refuses more with 422). */
export const STUDENT_INVITE_MAX = 50;

export type StudentInviteResult = "invited" | "already_enrolled" | "invalid_email" | "duplicate";

/** One row per submitted address, in order; the same shape whether or not the address has an account. */
export interface StudentInviteRowOut {
  email: string;
  result: StudentInviteResult;
  invitation: InvitationOut | null;
}

export interface StudentInvitationsOut {
  items: StudentInviteRowOut[];
  invited: number;
  already_enrolled: number;
  invalid: number;
}

export const createStudentInvitations = (courseId: string, body: { emails: string[]; message?: string; language: Lang }) =>
  post<StudentInvitationsOut>(`/courses/${enc(courseId)}/students/invitations`, body);
export const listStudentInvitations = (courseId: string, p: ListParams & { state?: InvitationState } = {}) =>
  lmsFetch<PageOut<InvitationOut>>(`/courses/${enc(courseId)}/students/invitations`, { params: { limit: 25, ...p } })
    .then((x) => asPage<InvitationOut>(x));
export const revokeStudentInvitation = (courseId: string, id: string) =>
  post<InvitationOut>(`/courses/${enc(courseId)}/students/invitations/${enc(id)}/revoke`);
export const resendStudentInvitation = (courseId: string, id: string) =>
  post<InvitationCreatedOut>(`/courses/${enc(courseId)}/students/invitations/${enc(id)}/resend`);

/** Split a pasted list (new lines, commas, semicolons, spaces) into distinct addresses, lowercased. */
export function splitEmails(text: string): string[] {
  const seen = new Set<string>();
  for (const part of text.split(/[\s,;]+/)) {
    const v = part.trim().toLowerCase();
    if (v) seen.add(v);
  }
  return Array.from(seen);
}

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Roster import limits shown in the UI; the server enforces them. */
export const ROSTER_LIMITS = { rows: 500, kib: 256 } as const;

/** `counts` of a roster import: S1's `RosterCounts` plus `added` (teachers with an account added directly). */
export type RosterImportCounts = RosterCounts & { added?: number };
export type RosterImport = Omit<RosterImportOut, "counts"> & { counts: RosterImportCounts };

export interface RosterUploadParams {
  file: File;
  kind: RosterKind;
  courseId?: string | null;
  departmentId?: string | null;
  /** Language of the invitation emails (the UI language). */
  language: Lang;
}

async function rosterPost(path: string, form: FormData): Promise<RosterImport> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST", headers: { ...(await getAuthHeader()) }, body: form, cache: "no-store",
    });
  } catch {
    throw new LmsApiError(0, "network", "Network error");
  }
  const text = await res.text();
  let data: unknown = undefined;
  if (text) {
    try { data = JSON.parse(text); } catch { data = undefined; }
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | undefined)?.error;
    if (err && typeof err.code === "string") throw new LmsApiError(res.status, err.code, err.message || err.code, err.details || {});
    const code = res.status === 413 ? "roster_too_large" : res.status === 429 ? "rate_limited" : res.status === 403 ? "forbidden" : res.status === 404 ? "not_found" : "unknown";
    throw new LmsApiError(res.status, code, `HTTP ${res.status}`);
  }
  return data as RosterImport;
}

/** Dry run: checks every row and saves only the masked report; sends nothing. */
export function checkRoster(orgId: string, p: RosterUploadParams): Promise<RosterImport> {
  const form = new FormData();
  form.append("file", p.file);
  form.append("kind", p.kind);
  if (p.courseId) form.append("course_id", p.courseId);
  if (p.departmentId) form.append("department_id", p.departmentId);
  form.append("dry_run", "true");
  form.append("language", p.language);
  return rosterPost(`/org/${enc(orgId)}/roster-imports`, form);
}

/** Apply a checked import: the same file again (the server compares the hash); idempotent. */
export function applyRoster(orgId: string, importId: string, file: File, language: Lang): Promise<RosterImport> {
  const form = new FormData();
  form.append("file", file);
  form.append("language", language);
  return rosterPost(`/org/${enc(orgId)}/roster-imports/${enc(importId)}/apply`, form);
}

export const listRosterImports = (orgId: string, p: ListParams = {}) =>
  lmsFetch<PageOut<RosterImport>>(`/org/${enc(orgId)}/roster-imports`, { params: { limit: 25, ...p } }).then((x) => asPage<RosterImport>(x));
export const getRosterImport = (orgId: string, id: string) =>
  lmsFetch<RosterImport>(`/org/${enc(orgId)}/roster-imports/${enc(id)}`);
// --- Phase 9 S3 end ---
