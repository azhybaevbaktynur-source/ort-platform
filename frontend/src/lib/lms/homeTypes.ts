// Student home: `GET /me/home` (PHASE_6_DESIGN 8.4; backend app/lms/home/schemas.py). Server-limited lists:
// in_progress, next_up and latest_results hold at most 3 rows, courses at most 10 (courses_total counts all).
import type { Num, SchemeLabelValue, SchemeType } from "./gradingTypes";
import type { Lang, LocalizedText } from "./types";

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
  labels: Record<string, SchemeLabelValue>;
  scheme_type: SchemeType | null;
  /** what `display_value` reads against ("7 / 10", "132 / 245"); null for percent and label schemes */
  max_value: Num | null;
  released_at: string;
  kept_attempt_id: string | null;
  /** the kept attempt beats every other attempt on this assessment (more than one attempt) */
  is_personal_best: boolean;
}

export interface HomeCourseOut {
  id: string;
  title: LocalizedText;
  description: LocalizedText | null;
  languages: Lang[];
  default_language: Lang;
  owner_display_name: string;
  /** root organization; null for a personal one */
  organization_display_name: string | null;
  is_platform_course: boolean;
  next_due_at: string | null;
  in_progress: boolean;
  /** requirements done / total, as the student's Modules page counts them; null: nothing to finish, no bar */
  progress: { done: number; total: number } | null;
  /** Student UI U2: `exam_prep` courses go in the student shell's exam switcher (optional: older backend). */
  student_layout?: "exam_prep" | "general";
  /** Student UI U9: what an exam-prep course has for the shell's menu (null for other courses; absent: older backend). */
  features?: { modules: boolean; practice: boolean } | null;
  /** F7a: public WebP cover (16:9, at most 1280 x 720); null: draw the generated default cover. Absent: older backend. */
  cover_url?: string | null;
  /** F7a: published exams with a published version, as the Tests page lists them (no practice quizzes) */
  tests_count?: number;
  /** F7a: lessons (page, file, link) of published modules */
  lessons_count?: number;
}

/** UX rework: one "To do" row of the dashboard. `attempt_id`: an attempt in progress. Dates are the caller's own. */
export interface HomeTodoOut {
  kind: "none" | "text" | "file" | "quiz";
  assignment_id: string | null;
  assessment_id: string | null;
  attempt_id: string | null;
  course_id: string;
  course_title: LocalizedText;
  title: LocalizedText;
  due_at: string | null;
  available_until: string | null;
  overdue: boolean;
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
  /** Phase 9 S4: the newest three pending applications (absent before Phase 9; never answers) */
  pending_applications?: HomePendingApplicationOut[];
  /** UX rework: at most 20 rows, in-progress attempts first, then soonest due (absent on an older backend) */
  todo?: HomeTodoOut[];
  /** Accounts: null unless there is something to say about the person's teacher application. */
  teacher_application?: HomeTeacherApplicationOut | null;
  /** Exam prep S2: open platform courses the student is not in ("From the platform"); optional: older backend. */
  platform_courses?: HomePlatformCourseOut[];
}

/** Exam prep S2: a platform course card with the one-tap join. */
export interface HomePlatformCourseOut {
  id: string;
  title: LocalizedText;
  description: LocalizedText | null;
  languages: Lang[];
  default_language: Lang;
  owner_display_name: string;
  organization_display_name: string | null;
  is_platform_course: boolean;
  /** F7a: public WebP cover (16:9, at most 1280 x 720); null: draw the generated default cover. Absent: older backend. */
  cover_url?: string | null;
  /** F7a: published exams with a published version, as the Tests page lists them (no practice quizzes) */
  tests_count?: number;
  /** F7a: lessons (page, file, link) of published modules */
  lessons_count?: number;
}

export interface HomeTeacherApplicationOut {
  status: "pending" | "approved" | "rejected" | "revoked";
  decided_at: string | null;
  reason: string | null;
  reapply_available_at: string | null;
}

/** Phase 9 S4: one "Pending applications" row on the student home. */
export interface HomePendingApplicationOut {
  application_id: string;
  course_id: string;
  course_title: LocalizedText;
  submitted_at: string;
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
  /** Phase 8a UX: the item's target ids (backend `ItemLinkOut`); used to drop rows already shown above */
  link?: { assignment_id?: string | null; assessment_id?: string | null } | null;
}
// --- Phase 8a S4a end ---
