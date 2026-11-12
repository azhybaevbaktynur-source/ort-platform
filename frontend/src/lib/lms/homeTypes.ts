// Student home: `GET /me/home` (PHASE_6_DESIGN 8.4; backend app/lms/home/schemas.py). Server-limited lists:
// in_progress, next_up and latest_results hold at most 3 rows, courses at most 10 (courses_total counts all).
import type { Num, SchemeLabelValue, SchemeType } from "./gradingTypes";
import type { ExamFamily, ExamSubject, Lang, LocalizedText } from "./types";
import type { ItemLinkOut } from "./modulesTypes";

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
  /** Student UI U9; step 3a S1: the six tab flags of `GET /courses/{id}`, for every course (absent: older backend). */
  features?: HomeCourseFeaturesOut | null;
  /** F7a: public WebP cover (16:9, at most 1280 x 720); null: draw the generated default cover. Absent: older backend. */
  cover_url?: string | null;
  /** F7a: published exams with a published version, as the Tests page lists them (no practice quizzes) */
  tests_count?: number;
  /** F7a: lessons (page, file, link) of published modules */
  lessons_count?: number;
  /** TEACHER_TO_STUDENT_MAP §2.3: the exam course this lesson course is attached to (absent: older backend). */
  exam_course_id?: string | null;
  // --- Step 3a S1 (STUDENT_IA_DESIGN §6.2.2): the hub's grouped cards; absent: older backend ---
  /** the card's group: null = «Другие курсы» */
  exam_family?: ExamFamily | null;
  /** null = the family's main course */
  subject?: ExamSubject | null;
  /** exam-prep courses only (ISO date): the card's countdown */
  exam_date?: string | null;
  /** the card's one button */
  next_step?: HomeNextStepOut | null;
  /** the newest released result of the course ("132 / 245") */
  last_result?: HomeLastResultOut | null;
}

/** Step 3a S1: `CourseFeaturesOut` of `GET /courses/{id}`, every flag present. */
export interface HomeCourseFeaturesOut {
  modules: boolean;
  files: boolean;
  announcements: boolean;
  practice: boolean;
  tests: boolean;
  hand_ins: boolean;
}

/** Step 3a S1: first that applies: the open attempt, the course's `modules_next` row, its first startable assignment,
 * else the course page. Titles are `{lang: text}`. */
export interface HomeNextStepOut {
  kind: "resume_test" | "continue_lesson" | "start" | "open";
  title: LocalizedText | null;
  /** resume_test */
  attempt_id: string | null;
  /** resume_test; start of a quiz */
  assessment_id: string | null;
  /** start */
  assignment_id: string | null;
  assignment_kind: "none" | "text" | "file" | "quiz" | null;
  /** continue_lesson */
  module_id: string | null;
  item_id: string | null;
  item_kind: string | null;
  link: ItemLinkOut | null;
  is_video: boolean;
}

/** Step 3a S1: the course's newest released result, by the same student gate as `latest_results`. */
export interface HomeLastResultOut {
  value: Num | null;
  max_value: Num | null;
  label: string | null;
  labels: Record<string, SchemeLabelValue>;
  scheme_type: SchemeType | null;
  at: string;
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
  /** F7: a platform course with a published paid test (the card's "Pro" mark) */
  has_paid_tests?: boolean;
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
  /** Phase 8a UX: the item's target ids (backend `ItemLinkOut`); used to drop rows already shown above.
   * TEACHER_TO_STUDENT_MAP S3: the home's "Продолжить урок" strip opens it (`itemHref`). */
  link?: ItemLinkOut | null;
  /** TEACHER_TO_STUDENT_MAP G12: a video lesson (the row shows the video icon); absent on an older backend */
  is_video?: boolean;
}
// --- Phase 8a S4a end ---
