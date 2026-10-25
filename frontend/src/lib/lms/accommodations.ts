// Phase 7a S5: accommodations, per-assignment exceptions and the quiz access code
// (docs/phases/PHASE_7A_DESIGN.md sections 2.4, 2.5, 2.7, 3.8 and 4.4).
import { lmsFetch } from "./client";
import type { PageOut, Lang } from "./types";
import type { PreviewStartOut } from "./assessmentTypes";

// The access-code fields extend the Phase 3 assessment shapes (declaration merging; optional so an older
// backend without them keeps working).
declare module "./assessmentTypes" {
  interface AssessmentStaffSummaryOut {
    /** the code itself is never sent */
    has_access_code?: boolean;
  }
  interface AssessmentLobbyOut {
    requires_access_code?: boolean;
  }
  interface AssessmentUpdateIn {
    /** string sets, null clears, absent leaves it unchanged */
    access_code?: string | null;
  }
}

export const ACCESS_CODE_MIN = 6; // security review 7a (server: 422 access_code_too_short)
export const ACCESS_CODE_MAX = 32;
/** Normalized like the server: trimmed, printable ASCII. */
export function accessCodeIssue(code: string): "too_short" | "too_long" | "invalid_chars" | null {
  const c = code.trim();
  if (c.length < ACCESS_CODE_MIN) return "too_short";
  if (c.length > ACCESS_CODE_MAX) return "too_long";
  if (!/^[\x20-\x7e]+$/.test(c)) return "invalid_chars";
  return null;
}

export const EXTRA_TIME_PERCENT_MAX = 300;
export const EXTRA_TIME_S_MAX = 86400;
export const EXTRA_ATTEMPTS_MAX = 100;
export const NOTE_MAX = 500;

export interface AccommodationOut {
  enrollment_id?: string;
  extra_time_percent: number;
  extra_time_s: number;
  extra_attempts: number;
  /** staff only */
  note: string | null;
  updated_at?: string | null;
  /** Q1 switch: false = extra time is stored but ORT exams ignore it */
  preset_exams_get_extra_time?: boolean;
}

/** `UserBrief` on staff rows. */
export interface UserBriefOut {
  id: string;
  display_name: string;
  email: string;
}

export interface AccommodationIn {
  extra_time_percent: number;
  extra_time_s: number;
  extra_attempts: number;
  note?: string | null;
}

/** One student of `GET /courses/{c}/accommodations` (roster-paginated; wire: `{enrollment_id, user, accommodation}`).
 * `user_id`, `student_name` and `email` are copied from `user` by this client for the screens. */
export interface AccommodationRowOut {
  enrollment_id: string;
  user: UserBriefOut;
  user_id: string;
  student_name: string | null;
  email: string | null;
  accommodation: AccommodationOut | null;
}

export interface OverrideOut {
  id: string;
  assignment_id: string;
  enrollment_id: string;
  user: UserBriefOut;
  /** copied from `user.display_name` by this client */
  student_name: string | null;
  due_at: string | null;
  available_from: string | null;
  available_until: string | null;
  extra_time_percent: number | null;
  extra_time_s: number | null;
  extra_attempts: number | null;
  note: string | null;
  updated_at?: string | null;
}

export interface OverrideIn {
  due_at: string | null;
  available_from: string | null;
  available_until: string | null;
  extra_time_percent: number | null;
  extra_time_s: number | null;
  extra_attempts: number | null;
  note?: string | null;
}

const e = encodeURIComponent;
const course = (c: string) => `/courses/${e(c)}`;

type Wire<T> = Omit<T, "user_id" | "student_name" | "email">;
const withName = <T extends { user: UserBriefOut }>(r: T) => ({ ...r, student_name: r.user?.display_name || null });

export async function listAccommodations(courseId: string, opts: { cursor?: string | null; limit?: number } = {}): Promise<PageOut<AccommodationRowOut>> {
  const page = await lmsFetch<PageOut<Wire<AccommodationRowOut>>>(`${course(courseId)}/accommodations`, { params: { cursor: opts.cursor, limit: opts.limit } });
  return { ...page, items: page.items.map((r) => ({ ...withName(r), user_id: r.user.id, email: r.user.email || null })) };
}
export const setAccommodation = (courseId: string, enrollmentId: string, body: AccommodationIn) =>
  lmsFetch<AccommodationOut>(`${course(courseId)}/enrollments/${e(enrollmentId)}/accommodations`, { method: "PUT", body });
export const clearAccommodation = (courseId: string, enrollmentId: string) =>
  lmsFetch<void>(`${course(courseId)}/enrollments/${e(enrollmentId)}/accommodations`, { method: "DELETE" });

/** All exceptions of one assignment (cursor pages of 50, read to the end). */
export async function listOverrides(courseId: string, assignmentId: string): Promise<OverrideOut[]> {
  const out: OverrideOut[] = [];
  let cursor: string | null = null;
  for (let i = 0; i < 40; i++) {
    const page: PageOut<Wire<OverrideOut>> = await lmsFetch<PageOut<Wire<OverrideOut>>>(
      `${course(courseId)}/assignments/${e(assignmentId)}/overrides`, { params: { limit: 50, cursor } });
    out.push(...page.items.map(withName));
    cursor = page.next_cursor;
    if (!cursor) break;
  }
  return out;
}
export const setOverride = async (courseId: string, assignmentId: string, enrollmentId: string, body: OverrideIn): Promise<OverrideOut> =>
  withName(await lmsFetch<Wire<OverrideOut>>(`${course(courseId)}/assignments/${e(assignmentId)}/overrides/${e(enrollmentId)}`, { method: "PUT", body }));
export const clearOverride = (courseId: string, assignmentId: string, enrollmentId: string) =>
  lmsFetch<void>(`${course(courseId)}/assignments/${e(assignmentId)}/overrides/${e(enrollmentId)}`, { method: "DELETE" });

/** Student start/resume with an optional access code (`StartIn.access_code`, section 3.8). */
export const startAttemptWithCode = (courseId: string, assessmentId: string, language?: Lang, accessCode?: string) =>
  lmsFetch<PreviewStartOut>(`${course(courseId)}/assessments/${e(assessmentId)}/attempts`, {
    method: "POST",
    body: { ...(language ? { language } : {}), ...(accessCode ? { access_code: accessCode.trim() } : {}) },
  });

/** "+25 % time, +10 min, +1 attempt" parts for a roster badge. */
export function accommodationParts(a: Pick<AccommodationOut, "extra_time_percent" | "extra_time_s" | "extra_attempts"> | null | undefined): {
  percent: number; minutes: number; attempts: number;
} | null {
  if (!a) return null;
  const percent = a.extra_time_percent || 0;
  const minutes = Math.round((a.extra_time_s || 0) / 60);
  const attempts = a.extra_attempts || 0;
  if (!percent && !minutes && !attempts) return null;
  return { percent, minutes, attempts };
}
