// Invitations API (docs/phases/PHASE_6_DESIGN.md §2.3, §7).
import { lmsFetch } from "./client";
import { asPage, type ListParams } from "./organizations";
import type { Lang, PageOut } from "./types";

const enc = encodeURIComponent;
const post = <T,>(path: string, body?: unknown) => lmsFetch<T>(path, { method: "POST", body: body ?? {} });

export type InvitationRole = "org_admin" | "teacher" | "assistant";
export type InvitationState = "pending" | "accepted" | "revoked" | "expired";

export interface InvitationOut {
  id: string;
  email: string;
  role: InvitationRole;
  state: InvitationState;
  invited_by_name: string | null;
  created_at: string;
  expires_at: string;
  course_title?: string | null;
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
  course_title?: string | null;
  masked_email: string;
  expires_at: string;
}

/** POST /invitations/{token}/accept result (assumed; used only to pick the redirect). */
export interface InvitationAcceptOut {
  organization_id?: string | null;
  course_id?: string | null;
  role?: InvitationRole;
}

/** GET /me/invitations item (assumed shape). */
export interface MyInvitationOut {
  id: string;
  organization_name: string;
  role: InvitationRole;
  course_title?: string | null;
  expires_at: string;
}

export const listOrgInvitations = (orgId: string, p: ListParams & { state?: InvitationState } = {}) =>
  lmsFetch<PageOut<InvitationOut> | InvitationOut[]>(`/org/${enc(orgId)}/invitations`, { params: { limit: 50, ...p } }).then((x) => asPage<InvitationOut>(x));
export const createOrgInvitation = (orgId: string, body: OrgInvitationIn) =>
  post<InvitationOut>(`/org/${enc(orgId)}/invitations`, body);
export const revokeOrgInvitation = (orgId: string, id: string) =>
  post<InvitationOut>(`/org/${enc(orgId)}/invitations/${enc(id)}/revoke`);
export const resendOrgInvitation = (orgId: string, id: string) =>
  post<InvitationOut>(`/org/${enc(orgId)}/invitations/${enc(id)}/resend`);

export const getInvitation = (token: string) => lmsFetch<InvitationPublicOut>(`/invitations/${enc(token)}`);
export const acceptInvitation = (token: string) => post<InvitationAcceptOut>(`/invitations/${enc(token)}/accept`);
export const listMyInvitations = () =>
  lmsFetch<PageOut<MyInvitationOut> | MyInvitationOut[]>("/me/invitations").then((x) => asPage<MyInvitationOut>(x).items);

/** Course owner invites a co-teacher or assistant who has no account yet. */
export const createCourseStaffInvitation = (courseId: string, body: { email: string; role: "teacher" | "assistant"; language: Lang }) =>
  post<InvitationOut>(`/courses/${enc(courseId)}/staff/invitations`, body);
