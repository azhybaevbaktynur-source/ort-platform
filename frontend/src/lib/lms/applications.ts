// Phase 9 S4: enrollment applications (docs/phases/PHASE_9_DESIGN.md §4.7, §4.9, §5, §6).
// Answers are PII of possible minors: never log them, never keep them in browser storage.
import { lmsFetch, isLmsApiError } from "./client";
import type {
  AnswerValue, ApplicationOut, ApplicationOwnOut, ApplicationStaffOut, ApplicationStatus, DecisionIn, PageOut,
} from "./types";

const enc = encodeURIComponent;
const base = (courseId: string) => `/courses/${enc(courseId)}/applications`;

export const submitApplication = (courseId: string, formId: string, answers: Record<string, AnswerValue>) =>
  lmsFetch<ApplicationOwnOut>(base(courseId), { method: "POST", body: { form_id: formId, answers } });

export const listApplications = (
  courseId: string,
  opts: { status?: ApplicationStatus | ""; q?: string; cursor?: string | null; limit?: number } = {},
) =>
  lmsFetch<PageOut<ApplicationOut>>(base(courseId), {
    params: { status: opts.status || undefined, q: opts.q?.trim() || undefined, cursor: opts.cursor, limit: opts.limit ?? 25 },
  });

/** Course staff get answers and fields; org admins get the status row only (no `answers` key). */
export const getApplication = (courseId: string, applicationId: string) =>
  lmsFetch<ApplicationStaffOut | ApplicationOut>(`${base(courseId)}/${enc(applicationId)}`);

export const hasAnswersPayload = (a: ApplicationStaffOut | ApplicationOut): a is ApplicationStaffOut => "fields" in a;

export const approveApplication = (courseId: string, applicationId: string, body: DecisionIn) =>
  lmsFetch<ApplicationOut>(`${base(courseId)}/${enc(applicationId)}/approve`, { method: "POST", body });
export const rejectApplication = (courseId: string, applicationId: string, body: DecisionIn) =>
  lmsFetch<ApplicationOut>(`${base(courseId)}/${enc(applicationId)}/reject`, { method: "POST", body });
export const withdrawApplication = (courseId: string, applicationId: string) =>
  lmsFetch<ApplicationOwnOut>(`${base(courseId)}/${enc(applicationId)}/withdraw`, { method: "POST" });

export const listMyApplications = (cursor?: string | null, limit = 25) =>
  lmsFetch<PageOut<ApplicationOwnOut>>("/me/applications", { params: { cursor, limit } });

export const DECISION_NOTE_MAX = 500;

/** `{field_key: code}` from a 422 submit error (codes: required, too_long, bad_option, bad_format). */
export function answerErrors(e: unknown): Record<string, string> | null {
  if (!isLmsApiError(e) || e.status !== 422) return null;
  const details = e.details as unknown;
  if (!Array.isArray(details)) return null;
  const out: Record<string, string> = {};
  for (const d of details) {
    if (d && typeof d === "object" && typeof d.field_key === "string" && typeof d.type === "string") {
      out[d.field_key] = d.type;
    }
  }
  return Object.keys(out).length ? out : null;
}
