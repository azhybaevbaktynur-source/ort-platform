// Phase 10 S6: course and organization analytics API client (PHASE_10_DESIGN 6). Aggregates only.
import { lmsFetch } from "./client";
import type { LocalizedText, PageOut } from "./types";

const e = encodeURIComponent;

export interface ScoreOut { count: number; mean_percent: number | null; distribution: number[] }
export interface SubmissionCountsOut { graded: number; pending_review: number; excused: number; missing: number }
export interface CourseAnalyticsOut {
  students: number; modules_total: number; completed_all: number; score: ScoreOut; submissions: SubmissionCountsOut;
}
export interface ModuleRowOut {
  module_id: string; title: LocalizedText; position: number;
  locked: number; unlocked: number; started: number; completed: number; not_started: number;
}
export interface AssignmentRowOut {
  assignment_id: string; assessment_id: string | null; kind: string; title: LocalizedText; due_at: string | null;
  students: number; submitted: number; graded: number; pending_review: number; excused: number; missing: number;
  late: number; mean_percent: number | null;
}
export interface QuizRollupRowOut {
  assessment_id: string; title: LocalizedText; preset: string; is_practice: boolean;
  attempts: number; students: number; mean_percent: number | null;
}
export interface OrgQuizRollupRowOut extends QuizRollupRowOut { course_id: string; course_title: LocalizedText }
export interface OrgAnalyticsOut { courses: number; students: number; score: ScoreOut; submissions: SubmissionCountsOut }
export interface OrgCourseRowOut {
  course_id: string; title: LocalizedText; department_name: string; students: number; completed_all: number;
  mean_percent: number | null; submitted: number; missing: number;
}

type Page = { cursor?: string | null; limit?: number };
const cbase = (c: string) => `/courses/${e(c)}/analytics`;
const obase = (o: string) => `/org/${e(o)}/analytics`;

export const getCourseAnalytics = (courseId: string) => lmsFetch<CourseAnalyticsOut>(`${cbase(courseId)}/overview`);
export const listModuleAnalytics = (courseId: string, p: Page = {}) =>
  lmsFetch<PageOut<ModuleRowOut>>(`${cbase(courseId)}/modules`, { params: { cursor: p.cursor, limit: p.limit } });
export const listAssignmentAnalytics = (courseId: string, p: Page = {}) =>
  lmsFetch<PageOut<AssignmentRowOut>>(`${cbase(courseId)}/assignments`, { params: { cursor: p.cursor, limit: p.limit } });
export const listQuizAnalytics = (courseId: string, p: Page = {}) =>
  lmsFetch<PageOut<QuizRollupRowOut>>(`${cbase(courseId)}/quizzes`, { params: { cursor: p.cursor, limit: p.limit } });

export const getOrgAnalytics = (orgId: string) => lmsFetch<OrgAnalyticsOut>(`${obase(orgId)}/overview`);
export const listOrgCourseAnalytics = (orgId: string, p: Page & { department_id?: string | null } = {}) =>
  lmsFetch<PageOut<OrgCourseRowOut>>(`${obase(orgId)}/courses`, { params: { cursor: p.cursor, limit: p.limit, department_id: p.department_id } });
export const listOrgQuizAnalytics = (orgId: string, p: Page = {}) =>
  lmsFetch<PageOut<OrgQuizRollupRowOut>>(`${obase(orgId)}/quizzes`, { params: { cursor: p.cursor, limit: p.limit } });
