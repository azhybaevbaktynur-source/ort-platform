// Invitations API (docs/phases/PHASE_6_DESIGN.md §2.3, §7).
import { lmsFetch } from "./client";
import { asPage, type ListParams } from "./organizations";
import type { Lang, LocalizedText, PageOut } from "./types";

const enc = encodeURIComponent;
const post = <T,>(path: string, body?: unknown) => lmsFetch<T>(path, { method: "POST", body: body ?? {} });

export type InvitationRole = "org_admin" | "teacher" | "assistant";
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
