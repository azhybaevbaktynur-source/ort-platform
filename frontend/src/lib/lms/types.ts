// TypeScript mirrors of the Phase 1 API schemas (docs/phases/PHASE_1_DESIGN.md section 5).
// Single source of truth for S4 and S5.

export type Lang = "en" | "ru" | "ky";
export const LMS_LANGS: Lang[] = ["en", "ru", "ky"];

export type LocalizedText = Partial<Record<Lang, string>>;

export type TeacherStatus = "none" | "pending" | "approved" | "revoked";
export type CourseStatus = "draft" | "published" | "concluded";
export type CourseRole = "teacher" | "assistant" | "student";
export type EnrollmentState = "active" | "removed" | "invited" | "completed" | string;
export type EnrollmentMode = "invite_code" | "closed" | "open" | "form_auto" | "form_review";
export type Visibility = "private" | "catalog";
export type TeacherRequestStatus = "pending" | "approved" | "rejected" | "cancelled";

export interface PageOut<T> {
  items: T[];
  next_cursor: string | null;
}

// 5.1 Me and teacher requests
export interface MeOut {
  id: string;
  email: string;
  display_name: string | null;
  locale: Lang;
  is_platform_admin: boolean;
  teacher_status: TeacherStatus;
  can_create_courses: boolean;
  /** Phase 6 S8: teaches somewhere (approved, org teacher/admin, or course staff); shows the Teaching area. */
  is_teacher: boolean;
}
export interface MePatchIn {
  locale: Lang;
}
export interface TeacherRequestIn {
  message?: string;
}
export interface MyTeacherRequestOut {
  id: string;
  message: string | null;
  status: TeacherRequestStatus;
  reason: string | null;
  created_at: string;
  decided_at: string | null;
}

// 5.2 Courses
export interface UserBrief {
  id: string;
  display_name: string | null;
  email: string;
}

export interface CourseCard {
  id: string;
  title: LocalizedText;
  languages: Lang[];
  default_language: Lang;
  status: CourseStatus;
  my_role: CourseRole | null;
  owner_display_name: string | null;
  starts_at: string | null;
  ends_at: string | null;
  deleted_at?: string | null;
}

export interface MyEnrollmentOut {
  id: string;
  course_id: string;
  role: CourseRole;
  state: EnrollmentState;
  activated_at: string | null;
  /** Phase 6b: set by getCourse when the viewer has no enrollment (org/platform admin reading the course). */
  read_only?: boolean;
}

export interface CourseStudentOut {
  id: string;
  title: LocalizedText;
  description: LocalizedText | null;
  languages: Lang[];
  default_language: Lang;
  status: CourseStatus;
  starts_at: string | null;
  ends_at: string | null;
  owner_display_name: string | null;
  my_enrollment: MyEnrollmentOut;
}

export interface CourseStaffOut extends CourseStudentOut {
  join_code: string;
  enrollment_mode: EnrollmentMode;
  enrollment_limit: number | null;
  visibility: Visibility;
  unlisted_by_admin: boolean;
  active_student_count: number;
  owner: UserBrief;
  is_owner: boolean;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  concluded_at: string | null;
  /** Phase 8b S5: set when the course is an exam template's hidden sandbox (sample quiz + previews). */
  sandbox_for_template_id?: string | null;
}

/** Either serializer; discriminate with `isStaffCourse`. */
export type CourseOut = CourseStaffOut | CourseStudentOut;

export function isStaffCourse(c: CourseOut): c is CourseStaffOut {
  return "join_code" in c;
}

export interface CourseCreateIn {
  title: LocalizedText;
  description?: LocalizedText;
  languages: Lang[];
  default_language: Lang;
  enrollment_mode?: "invite_code" | "closed";
  enrollment_limit?: number | null;
  starts_at?: string | null;
  ends_at?: string | null;
}

export interface CourseUpdateIn {
  title?: LocalizedText;
  description?: LocalizedText;
  languages?: Lang[];
  default_language?: Lang;
  enrollment_mode?: "invite_code" | "closed";
  enrollment_limit?: number | null;
  starts_at?: string | null;
  ends_at?: string | null;
  visibility?: Visibility;
}

export interface JoinIn {
  code: string;
}
export interface JoinOut {
  course: CourseCard;
  enrollment: MyEnrollmentOut;
  already_enrolled: boolean;
}
export interface TransferIn {
  new_owner_user_id: string;
}
export interface JoinCodeOut {
  join_code: string;
}

export interface RosterEntryOut {
  enrollment_id: string;
  user: UserBrief;
  role: CourseRole;
  state: EnrollmentState;
  source: string;
  activated_at: string | null;
  removed_at: string | null;
  is_owner: boolean;
}
export interface StaffPublicOut {
  display_name: string;
  role: CourseRole;
}
export interface AddStaffIn {
  email: string;
  role: "teacher" | "assistant";
}
export interface RoleChangeIn {
  role: CourseRole;
}

// 5.3 Platform admin (used by S5)
export interface TeacherRequestAdminOut {
  id: string;
  user: UserBrief;
  user_teacher_status: TeacherStatus;
  message: string | null;
  status: TeacherRequestStatus;
  reason: string | null;
  created_at: string;
  decided_at: string | null;
  decided_by: UserBrief | null;
}
export interface AdminUserOut {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
  email_verified: boolean;
  is_platform_admin: boolean;
  teacher_status: TeacherStatus;
  disabled_at: string | null;
  disabled_reason: string | null;
}
export interface AdminUserDetailOut extends AdminUserOut {
  owned_courses: CourseCard[];
  active_enrollment_count: number;
  teacher_requests: TeacherRequestAdminOut[];
}
export interface AdminCourseOut {
  id: string;
  title: LocalizedText;
  owner: UserBrief;
  status: CourseStatus;
  visibility: Visibility;
  enrollment_mode: EnrollmentMode;
  unlisted_by_admin_at: string | null;
  active_student_count: number;
  created_at: string;
  deleted_at: string | null;
  deleted_by_id: string | null;
}
export interface AuditEntryOut {
  id: string;
  created_at: string;
  actor: UserBrief;
  action: string;
  target_type: string;
  target_id: string;
  reason: string | null;
  details: Record<string, unknown>;
}
export interface PlatformSummaryOut {
  pending_teacher_requests: number;
}

// Error codes (5.4); frontend keys are lms.errors.<code>
export const LMS_ERROR_CODES = [
  "not_found", "course_not_found", "forbidden", "owner_only", "owner_immutable", "owner_cannot_leave",
  "use_leave", "not_active", "teacher_not_approved", "not_approved_teacher", "invalid_new_owner",
  "join_code_invalid", "join_code_exhausted", "rate_limited", "already_enrolled", "user_not_found",
  "limit_below_current", "unlisted_by_admin", "invalid_transition", "has_students", "not_deleted",
  "already_deleted", "title_required", "already_teacher", "request_pending", "not_pending",
  "cannot_disable_self", "cannot_disable_admin", "platform_admin_required", "validation_failed",
  "invalid_cursor", "account_disabled", "network", "unknown",
  "bank_not_found", "question_not_found", "passage_not_found", "version_not_found",
  "asset_not_found", "version_conflict", "invalid_question_data", "unsupported_type",
  "asset_not_usable", "image_invalid", "image_too_large", "image_too_many_pixels",
  "storage_quota_exceeded", "storage_full", "language_not_in_course", "translation_language_taken",
  "translation_scope_mismatch", "translation_type_mismatch", "source_conflict", "bank_deleted",
  "passage_in_use", "invalid_move", "import_busy", "length_required",
  "private_storage_unavailable", "passage_deleted", "file_too_large", "assessment_not_found",
  "section_not_found", "item_not_found", "attempt_not_found", "draft_conflict",
  "languages_not_in_course", "too_many_sections", "too_many_items", "section_not_empty",
  "order_mismatch", "preset_rule_locked", "item_type_not_allowed", "item_language_mismatch",
  "item_duplicate", "passage_mismatch", "publish_invalid", "confirm_required", "not_published",
  "attempts_in_progress", "assessment_not_available", "attempts_exhausted",
  "language_not_available", "attempt_closed", "section_closed", "section_not_current",
  "use_submit", "invalid_response", "payload_too_large", "results_not_available",
  "attempt_not_submitted", "points_out_of_range", "after_close_needs_until",
  // Phase 8a S4a: module gating and course home (text in lms.errors.*)
  "module_locked", "prerequisite_invalid", "prerequisite_order", "home_page_invalid",
  // Phase 8a S5: pages, course files and announcements (S3 codes; also in pages/courseFiles/announcements.errors)
  "page_not_found", "page_variant_exists", "course_file_not_found", "announcement_not_found", "folder_invalid",
  "course_files_quota", "page_conflict", "already_published",
  // Phase 8c S1: a write sent in the read-only Student view
  "student_view_read_only",
] as const;
export type LmsErrorCode = (typeof LMS_ERROR_CODES)[number];

// --- Phase 6 S4 begin ---
// Phase 6a fields (docs/phases/PHASE_6_DESIGN.md §2.1, §5.3), merged into the interfaces above
// (declaration merging). Optional so that an older backend without them still works.

/** `CourseOut.template` (null = general course). Read it only through `templateUi()` in templates.ts. */
export interface CourseTemplateOut {
  key: string;
  version: number;
  locked: boolean;
  result_view: "general" | "ort";
  passage_display: "plain" | "numbered";
  section_keys: string[];
  assessment_presets: string[];
  importer_profiles: string[];
  title_key: string;
}

export interface CourseStudentOut {
  organization_id?: string | null;
  organization_name?: string | null;
  /** `undefined` = backend without templates (today's behaviour); `null` = general course. */
  template?: CourseTemplateOut | null;
}

export interface CourseCreateIn {
  organization_id?: string;
  owner_id?: string;
  template_key?: string | null;
}
// --- Phase 6 S4 end ---

// --- Phase 8a S4a begin --- (course home and student tabs, docs/phases/PHASE_8A_DESIGN.md 5.5, 8.2; optional so an
// older backend keeps today's layout)
export type HomeKind = "modules" | "page" | "assignments";

/** Which student tabs have published content (three EXISTS on the server). */
export interface CourseFeaturesOut {
  modules: boolean;
  files: boolean;
  announcements: boolean;
}

export interface CourseStudentOut {
  /** `undefined` (older backend) behaves as `assignments`: today's course home. */
  home_kind?: HomeKind;
  home_page_id?: string | null;
  features?: CourseFeaturesOut;
}

export interface CourseUpdateIn {
  home_kind?: HomeKind;
  home_page_id?: string | null;
}
// --- Phase 8a S4a end ---

// --- Phase 8c S1 begin --- (PHASE_8C_DESIGN §7: Course page reads; S2 builds the UI on these shapes)
export type UnsortedKind = "assignment" | "page" | "file";

export interface UnsortedVariantOut {
  id: string;
  language: Lang;
}

/** A live assignment, page group or course file that no live item of a live module references. */
export interface UnsortedItemOut {
  kind: UnsortedKind;
  id: string;
  /** LocalizedText for assignments; a plain string for pages (the listed variant's title) and files. */
  title: LocalizedText | string;
  published: boolean;
  assignment_kind?: "none" | "text" | "file" | "quiz" | null;
  assessment_id?: string | null;
  language?: Lang | null;
  translation_group_id?: string | null;
  variants?: UnsortedVariantOut[] | null;
  folder?: string | null;
  updated_at?: string | null;
}

export interface UnsortedPageOut {
  items: UnsortedItemOut[];
  next_cursor: string | null;
  total: number;
}

/** `GET /courses/{id}/modules/unsorted`; with `kind` only that page is set. */
export interface UnsortedOut {
  assignments: UnsortedPageOut | null;
  pages: UnsortedPageOut | null;
  files: UnsortedPageOut | null;
}

export interface TodoGradeOut {
  assignment_id: string;
  title: LocalizedText;
  kind: "none" | "text" | "file" | "quiz";
  needs_grading: number;
  oldest_submitted_at: string | null;
}

export interface TodoDraftOut {
  assignment_id: string;
  title: LocalizedText;
  kind: "none" | "text" | "file" | "quiz";
  assessment_id: string | null;
  updated_at: string | null;
}

/** `GET /courses/{id}/todo` (teacher, assistant): at most 10 rows per group plus the totals. */
export interface TodoOut {
  to_grade: TodoGradeOut[];
  to_grade_total: number;
  drafts: TodoDraftOut[];
  drafts_total: number;
  unpublished_modules: number;
  first_unpublished_module_id: string | null;
  active_students: number;
  /** Teachers only (assistants: null). */
  join_code: string | null;
  join_code_active: boolean;
}
// --- Phase 8c S1 end ---
