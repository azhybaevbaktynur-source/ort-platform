// Course templates (docs/phases/PHASE_6_DESIGN.md §5.3-§5.6). Components never test for "ort":
// they read `templateUi(course)` (or `useTemplateUi()` inside a course route).
import { useContext } from "react";
import { lmsFetch } from "./client";
import { ASSESSMENT_PRESETS, ORT_SUBJECT_KEYS, type AssessmentPreset } from "./assessmentTypes";
import { ORT_SECTIONS } from "./contentTypes";
import type { ImportExamType } from "./contentImport";
import type { CourseOut, CourseTemplateOut } from "./types";
import { CourseContext } from "@/components/lms/CourseContext";

export type { CourseTemplateOut } from "./types";

/** What the UI shows for a course, derived from `CourseOut.template`. */
export interface TemplateUi {
  /** Template key, null for a general course (and for a backend without templates). */
  key: string | null;
  /** Locked template: structure controls are disabled with `templates.lockedNote` (§5.4). */
  locked: boolean;
  resultView: "general" | "ort";
  passageDisplay: "plain" | "numbered";
  /** Section key suggestions (datalists). Empty = free labels, no datalist. */
  sectionKeys: readonly string[];
  /** Subject keys for the subject preset (subset of `sectionKeys`). */
  subjectKeys: readonly string[];
  /** Assessment preset radios; `["none"]` only = radios hidden. */
  assessmentPresets: AssessmentPreset[];
  /** Import formats (CSV/zip importer profiles); empty = no format select, `exam_type` null. */
  importerProfiles: ImportExamType[];
  /** Default import format ("" = general). */
  defaultImportProfile: ImportExamType | "";
}

const KNOWN_PROFILES: ImportExamType[] = ["full_main", "subject", "practice_bank"];

/** Order known keys like today's constant, unknown keys after them (stable). */
function ordered<T extends string>(known: readonly T[], keys: readonly string[]): string[] {
  const set = new Set(keys);
  return [...known.filter((k) => set.has(k)), ...keys.filter((k) => !(known as readonly string[]).includes(k))];
}

/** General course (template null), §5.6. */
export const GENERAL_UI: TemplateUi = Object.freeze({
  key: null,
  locked: false,
  resultView: "general",
  passageDisplay: "plain",
  sectionKeys: [],
  subjectKeys: [],
  assessmentPresets: ["none"],
  importerProfiles: [],
  defaultImportProfile: "",
}) as TemplateUi;

/**
 * Backend without the `template` field (or no course in context): exactly today's behaviour,
 * so nothing changes before the backend ships templates.
 */
export const LEGACY_UI: TemplateUi = Object.freeze({
  key: null,
  locked: false,
  resultView: "ort",
  passageDisplay: "numbered",
  sectionKeys: ORT_SECTIONS,
  subjectKeys: ORT_SUBJECT_KEYS,
  assessmentPresets: ASSESSMENT_PRESETS,
  importerProfiles: KNOWN_PROFILES,
  defaultImportProfile: "full_main",
}) as TemplateUi;

export function templateUiFrom(tpl: CourseTemplateOut | null | undefined): TemplateUi {
  if (tpl === undefined) return LEGACY_UI;
  if (tpl === null) return GENERAL_UI;
  const sectionKeys = ordered(ORT_SECTIONS, tpl.section_keys ?? []);
  const subjectKeys = ORT_SUBJECT_KEYS.filter((k) => sectionKeys.includes(k));
  const presets = ASSESSMENT_PRESETS.filter((p) => p === "none" || (tpl.assessment_presets ?? []).includes(p));
  const profiles = KNOWN_PROFILES.filter((p) => (tpl.importer_profiles ?? []).includes(p));
  return {
    key: tpl.key,
    locked: !!tpl.locked,
    resultView: tpl.result_view === "ort" ? "ort" : "general",
    passageDisplay: tpl.passage_display === "numbered" ? "numbered" : "plain",
    sectionKeys,
    subjectKeys,
    assessmentPresets: presets,
    importerProfiles: profiles,
    defaultImportProfile: profiles[0] ?? "",
  };
}

/** UI switches for a course; general defaults when `course.template` is null (§5.3). */
export function templateUi(course: Pick<CourseOut, "template"> | null | undefined): TemplateUi {
  if (!course) return LEGACY_UI;
  return templateUiFrom(course.template);
}

/** `templateUi` of the course of the current course route (today's behaviour outside a course). */
export function useTemplateUi(): TemplateUi {
  const ctx = useContext(CourseContext);
  return templateUi(ctx?.course);
}

/**
 * Preset rule lock (unchanged from Phase 3): sections of a preset assessment whose key is a known
 * preset section keep their type rules (server error `preset_rule_locked`).
 */
export function isPresetRuleLocked(preset: AssessmentPreset, key: string | null | undefined): boolean {
  return preset !== "none" && !!key && (ORT_SECTIONS as readonly string[]).includes(key);
}

/** i18n label key of an import profile (`bank.import.formats.*`). */
export function importProfileLabelKey(p: ImportExamType | ""): string {
  const map: Record<string, string> = { full_main: "ortMain", subject: "ortSubject", practice_bank: "ortPractice", "": "general" };
  return `bank.import.formats.${map[p] ?? "general"}`;
}

// --- API ---

/** GET /courses/templates?organization_id= : granted templates of that organization (general = no entry). */
export interface TemplateChoiceOut {
  key: string;
  title_key: string;
}
export const listCourseTemplates = (organizationId?: string | null) =>
  lmsFetch<TemplateChoiceOut[]>("/courses/templates", { params: { organization_id: organizationId } });

/** Template title: the backend's `title_key`, then `templates.names.<key>`, then the key itself. */
export function templateTitle(t: (k: string) => string, key: string, titleKey?: string | null): string {
  if (titleKey) {
    const v = t(titleKey);
    if (v !== titleKey) return v;
  }
  const k = `templates.names.${key}`;
  const v = t(k);
  return v !== k ? v : key;
}
