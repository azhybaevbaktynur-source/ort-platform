// Phase 8a S4a: modules API shapes (docs/phases/PHASE_8A_DESIGN.md 7.1; backend app/lms/modules/schemas.py).
// Every `title` is a LocalizedText dict (page and file titles are wrapped as `{language: title}` by the server).
import type { AssignmentKind, AssignmentStaffOut } from "./assignmentTypes";
import type { LocalizedText } from "./types";

export type ItemKind = "page" | "file" | "assignment" | "url" | "header";
export type RequirementType = "view" | "mark_done" | "submit" | "min_score" | "min_percent";
export type ModuleState = "locked" | "unlocked" | "started" | "completed";
export type CompletionMode = "all" | "any";
export type ModuleWarningCode =
  | "target_unpublished" | "target_deleted" | "prerequisite_unpublished" | "prerequisite_deleted"
  | "requirement_on_unpublished_target" | "unlock_in_past_with_locked_students" | "first_module_pro";
export type LockReasonKind = "unlock_at" | "prerequisite" | "sequential";
/** F5a (COURSE_LESSONS_DESIGN 2, 3): Pro module tier; why a student row is locked. */
export type AccessTier = "free" | "paid";
export type ItemLockedReason = "module" | "access_required";
/** F5a: `duration_s` range (the editor sends minutes x 60, 1..600 minutes). */
export const DURATION_S_MIN = 60;
export const DURATION_S_MAX = 36000;

export const ITEM_KINDS: ItemKind[] = ["page", "file", "assignment", "url", "header"];
export const THRESHOLD_REQUIREMENTS: RequirementType[] = ["min_score", "min_percent"];

/** Requirement types allowed for an item kind (service rule `requirement_kind_mismatch`; a header has none). */
export function requirementTypesFor(kind: ItemKind): RequirementType[] {
  if (kind === "header") return [];
  if (kind === "assignment") return ["view", "mark_done", "submit", "min_score", "min_percent"];
  return ["view", "mark_done"];
}

// ---- inputs ----
export interface ModuleIn {
  title: LocalizedText;
  published?: boolean;
  unlock_at?: string | null;
  sequential?: boolean;
  completion_mode?: CompletionMode;
  /** F5a: `paid` only in platform courses (422 otherwise) */
  access_tier?: AccessTier;
}
export type ModuleUpdateIn = Partial<ModuleIn>;

export interface RequirementIn {
  type: RequirementType;
  threshold?: number | null;
}

export interface ItemIn {
  kind: ItemKind;
  page_id?: string;
  file_id?: string;
  assignment_id?: string;
  url?: string;
  title_override?: LocalizedText | null;
  indent?: number;
  published?: boolean;
  position?: number;
  requirement?: RequirementIn | null;
  /** F5a: page / file / url only, 60..36000 seconds */
  duration_s?: number | null;
}

export interface ItemUpdateIn {
  title_override?: LocalizedText | null;
  indent?: number;
  published?: boolean;
  url?: string;
  /** F5a: `null` clears; page / file / url only */
  duration_s?: number | null;
}

// ---- shared ----
export interface ModuleWarningOut {
  code: ModuleWarningCode;
  module_id?: string | null;
  item_id?: string | null;
}

export interface LockReasonOut {
  kind: LockReasonKind;
  at?: string | null;
  module_id?: string | null;
  item_id?: string | null;
  title?: LocalizedText | null;
}

// ---- staff ----
export interface RequirementStaffOut {
  type: RequirementType;
  threshold: number | null;
}

export interface ItemTargetOut {
  title: LocalizedText | null;
  published: boolean;
  deleted: boolean;
  language?: string | null;
  assignment_kind?: AssignmentKind | null;
  assessment_id?: string | null;
}

export interface ItemStaffOut {
  id: string;
  module_id: string;
  kind: ItemKind;
  position: number;
  indent: number;
  title_override: LocalizedText | null;
  published: boolean;
  page_id: string | null;
  file_id: string | null;
  assignment_id: string | null;
  url: string | null;
  requirement: RequirementStaffOut | null;
  target: ItemTargetOut | null;
  warnings: ModuleWarningOut[];
  /** F5a */
  duration_s?: number | null;
}

export interface ModuleStaffOut {
  id: string;
  title: LocalizedText;
  position: number;
  published: boolean;
  unlock_at: string | null;
  sequential: boolean;
  completion_mode: CompletionMode;
  rules_version: number;
  prerequisites: string[];
  items: ItemStaffOut[];
  warnings: ModuleWarningOut[];
  deleted_at: string | null;
  /** F5a: tier, sum of the published items' durations, number of published lessons (page / file / url) */
  access_tier?: AccessTier;
  duration_s?: number;
  lessons_count?: number;
}

export interface ModulesStaffOut {
  modules: ModuleStaffOut[];
  /** F5c: the server accepts `access_tier = paid` here (platform course); the editor shows the Pro switch only then */
  is_platform_course?: boolean;
}

export interface QuizItemOut {
  item: ItemStaffOut;
  assignment: AssignmentStaffOut;
  assessment_id: string;
}

export interface ReapplyOut {
  cleared_students: number;
}

// ---- student (allow-lists) ----
export interface RequirementStudentOut {
  type: RequirementType;
  threshold: number | null;
  met: boolean;
  best_score_percent: number | null;
}

export interface ItemLinkOut {
  page_id?: string | null;
  file_id?: string | null;
  assignment_id?: string | null;
  assessment_id?: string | null;
  assignment_kind?: AssignmentKind | null;
  url?: string | null;
}

/** Student UI U7 (§4.4): an allowlisted YouTube / Vimeo url item; the player URL is built from `id` only. */
export interface VideoOut {
  provider: "youtube" | "vimeo";
  id: string;
}

export interface ItemStudentOut {
  id: string;
  kind: ItemKind;
  title: LocalizedText;
  indent: number;
  locked: boolean;
  requirement: RequirementStudentOut | null;
  link: ItemLinkOut | null;
  /** UX rework: assignment rows, the student's own due date (absent on an older backend) */
  due_at?: string | null;
  /** U7: set on unlocked url items that are YouTube / Vimeo videos (absent on an older backend) */
  video?: VideoOut | null;
  /** F5a: lesson length; done decided by the server (also on locked rows); why the row is locked */
  duration_s?: number | null;
  done?: boolean;
  locked_reason?: ItemLockedReason | null;
}

export interface ModuleStudentOut {
  id: string;
  title: LocalizedText;
  /** null for an org admin (student shape, never evaluated) */
  state: ModuleState | null;
  unlock_at: string | null;
  sequential: boolean;
  completion_mode: CompletionMode;
  current_position: number | null;
  lock_reasons: LockReasonOut[];
  items: ItemStudentOut[];
  /** F5a: Pro tier and whether it locks this module for the caller; done / total non-header rows; total duration */
  access_tier?: AccessTier;
  access_locked?: boolean;
  done?: number;
  total?: number;
  duration_s?: number;
}

/** F5a: the course bar (the same rows as the modules' done / total; tests count). */
export interface ProgressOut {
  done: number;
  total: number;
  duration_s: number;
}

export interface ItemRefOut {
  module_id: string;
  module_title: LocalizedText;
  item_id: string;
  kind: ItemKind;
  title: LocalizedText;
  link: ItemLinkOut | null;
}

export interface ModulesStudentOut {
  modules: ModuleStudentOut[];
  /** F5a: the first visible non-header item, in course order, that is neither locked nor done */
  up_next: ItemRefOut | null;
  progress?: ProgressOut;
}

/** `GET _C/modules` answers with the staff or the student shape; staff modules carry `rules_version`. */
export type ModulesOut = ModulesStaffOut | ModulesStudentOut;
export function isStaffModules(m: ModulesOut): m is ModulesStaffOut {
  return m.modules.length > 0 ? "rules_version" in m.modules[0] : !("up_next" in m);
}

// ---- pickers (minimal shapes of the pages / course files lists, read by the add-item dialog only) ----
export interface PagePickOut {
  id: string;
  language: string;
  title: string;
  published: boolean;
  deleted_at?: string | null;
}
export interface CourseFilePickOut {
  id: string;
  folder: string;
  title: string;
  published: boolean;
  deleted_at?: string | null;
}

/** Error codes of the modules routes (text in `modules.errors.<code>`). */
export const MODULE_ERROR_CODES = [
  "module_locked", "prerequisite_invalid", "prerequisite_order", "requirement_kind_mismatch", "url_invalid",
  "limit_reached", "order_incomplete", "home_page_invalid", "template_locked",
] as const;
