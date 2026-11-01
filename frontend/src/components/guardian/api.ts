// Phase 11 S2 (PHASE_11_DESIGN 4): the parent routes. Backend: app/lms/guardian/.
import { lmsFetch } from "@/lib/lms/client";
import type { Num } from "@/lib/lms/gradingTypes";
import type { LocalizedText, PageOut } from "@/lib/lms/types";

const e = encodeURIComponent;
const LINKS = "/guardian/links";

export interface GuardianLinkCreated {
  id: string;
  student_name: string;
  needs_consent: boolean;
}

export interface GuardianLink extends GuardianLinkCreated {
  created_at: string;
  holds_consent: boolean;
  under_14: boolean;
}

export interface GuardianCourse {
  id: string;
  title: LocalizedText;
}

export type GuardianGradeState = "graded" | "pending" | "missing" | "excused" | "hidden" | "not_started" | "submitted";

export interface GuardianGrade {
  title: LocalizedText;
  due_at: string | null;
  state: GuardianGradeState;
  points: Num | null;
  possible: Num | null;
  percent: Num | null;
  label: string | null;
}

export interface GuardianGrades {
  total: { percent: Num | null; label: string | null } | null;
  items: GuardianGrade[];
}

export interface GuardianDue {
  course_title: LocalizedText;
  title: LocalizedText;
  kind: string;
  due_at: string | null;
}

export interface GuardianAnnouncement {
  title: string;
  body_html: string;
  published_at: string | null;
}

export interface PolicyOut {
  id: string;
  kind: string;
  version: number;
  status: string;
  body: string;
}

export const redeemCode = (code: string) => lmsFetch<GuardianLinkCreated>(LINKS, { method: "POST", body: { code } });
export const listLinks = () => lmsFetch<GuardianLink[]>(LINKS);
export const removeLink = (id: string) => lmsFetch<void>(`${LINKS}/${e(id)}`, { method: "DELETE" });
export const giveConsent = (id: string, policyVersionId: string) =>
  lmsFetch<GuardianLink>(`${LINKS}/${e(id)}/consent`, { method: "POST", body: { policy_version_id: policyVersionId } });
export const withdrawConsent = (id: string) => lmsFetch<void>(`${LINKS}/${e(id)}/consent`, { method: "DELETE" });
export const requestDelete = (id: string) =>
  lmsFetch<{ id: string; status: string; due_at: string }>(`${LINKS}/${e(id)}/delete-request`, { method: "POST" });

export const listCourses = (id: string, cursor?: string | null) =>
  lmsFetch<PageOut<GuardianCourse>>(`${LINKS}/${e(id)}/courses`, { params: { cursor, limit: 100 } });
export const getGrades = (id: string, courseId: string) =>
  lmsFetch<GuardianGrades>(`${LINKS}/${e(id)}/courses/${e(courseId)}/grades`);
export const getDue = (id: string) => lmsFetch<GuardianDue[]>(`${LINKS}/${e(id)}/due`, { params: { limit: 50 } });
export const listAnnouncements = (id: string, courseId: string, cursor?: string | null) =>
  lmsFetch<PageOut<GuardianAnnouncement>>(`${LINKS}/${e(id)}/courses/${e(courseId)}/announcements`, { params: { cursor } });

export const currentPolicies = (locale: string) =>
  lmsFetch<PolicyOut[]>("/privacy/policies/current", { params: { locale } });
