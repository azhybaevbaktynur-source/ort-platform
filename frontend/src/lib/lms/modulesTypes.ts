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
  | "requirement_on_unpublished_target" | "unlock_in_past_with_locked_students";
export type LockReasonKind = "unlock_at" | "prerequisite" | "sequential";

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
}

export interface ItemUpdateIn {
  title_override?: LocalizedText | null;
  indent?: number;
  published?: boolean;
  url?: string;
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
}

export interface ModulesStaffOut {
  modules: ModuleStaffOut[];
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

export interface ItemStudentOut {
  id: string;
  kind: ItemKind;
  title: LocalizedText;
  indent: number;
  locked: boolean;
  requirement: RequirementStudentOut | null;
  link: ItemLinkOut | null;
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
  up_next: ItemRefOut | null;
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
