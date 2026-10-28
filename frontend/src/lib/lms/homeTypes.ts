// Student home: `GET /me/home` (PHASE_6_DESIGN 8.4; backend app/lms/home/schemas.py). Server-limited lists:
// in_progress, next_up and latest_results hold at most 3 rows, courses at most 10 (courses_total counts all).
import type { Num, SchemeType } from "./gradingTypes";
import type { LocalizedText } from "./types";

export interface HomeInProgressOut {
  attempt_id: string;
  assessment_id: string;
  assessment_title: LocalizedText;
  course_id: string;
  course_title: LocalizedText;
  started_at: string;
}

export interface HomeNextUpOut {
  // --- Phase 7a S5 begin --- (PHASE_7A_DESIGN 3.9: next up lists assignments)
  /** absent on a backend before Phase 7a (then the row is a quiz with `assessment_id`) */
  assignment_id?: string;
  kind?: "none" | "text" | "file" | "quiz";
  /** quiz rows only */
  assessment_id?: string | null;
  // --- Phase 7a S5 end ---
  course_id: string;
  course_title: LocalizedText;
  title: LocalizedText;
  due_at: string | null;
  available_until: string | null;
  /** null = unlimited attempts */
  attempts_left: number | null;
}

export interface HomeResultOut {
  // --- Phase 7a S5 begin --- (released manual grades are listed too)
  assignment_id?: string;
  kind?: "none" | "text" | "file" | "quiz";
  /** quiz results only */
  assessment_id?: string | null;
  // --- Phase 7a S5 end ---
  course_id: string;
  course_title: LocalizedText;
  title: LocalizedText;
  display_value: Num | null;
  label: string | null;
  scheme_type: SchemeType | null;
  released_at: string;
  kept_attempt_id: string | null;
  /** the kept attempt beats every other attempt on this assessment (more than one attempt) */
  is_personal_best: boolean;
}

export interface HomeCourseOut {
  id: string;
  title: LocalizedText;
  owner_display_name: string;
  is_platform_course: boolean;
  next_due_at: string | null;
  in_progress: boolean;
}

export interface HomeOut {
  in_progress: HomeInProgressOut[];
  next_up: HomeNextUpOut[];
  latest_results: HomeResultOut[];
  courses: HomeCourseOut[];
  courses_total: number;
  pending_invitations: number;
  // --- Phase 8a S4a begin --- (PHASE_8A_DESIGN 7.2: "up next" in modules, read from the progress cache)
  /** absent on a backend before Phase 8a */
  modules_next?: HomeModuleNextOut[];
  // --- Phase 8a S4a end ---
  /** Phase 8a S5: the latest three published announcements of the student's active courses (absent before 8a) */
  announcements?: HomeAnnouncementOut[];
}

/** Phase 8a S5: one row of the home announcements strip (backend `AnnouncementHomeOut`; never a body). */
export interface HomeAnnouncementOut {
  id: string;
  course_id: string;
  course_title: LocalizedText;
  title: string;
  published_at: string;
}

// --- Phase 8a S4a begin ---
/** "Continue in *Course*: *Item*": the first unlocked item with an unmet requirement in one course. */
export interface HomeModuleNextOut {
  course_id: string;
  course_title: LocalizedText;
  module_id: string;
  module_title?: LocalizedText;
  item_id: string;
  kind?: "page" | "file" | "assignment" | "url" | "header";
  title: LocalizedText;
}
// --- Phase 8a S4a end ---
