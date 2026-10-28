"use client";

// Phase 7b S4: shared bits of the exam template screens (errors, badges, labels).
import React, { useCallback } from "react";
import { Lock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { EXAM_TEMPLATE_ERROR_CODES, type ExamTemplateScope, type ExamTemplateStatus, type SpecIssue } from "@/lib/lms/examTemplateTypes";
import { apiErrorText } from "@/components/lms/org/OrgUi";
import { Badge, ErrorState, type BadgeTone } from "@/components/ui";

const KNOWN = new Set<string>(EXAM_TEMPLATE_ERROR_CODES);

export function isExamTemplateErrorCode(code: unknown): boolean {
  return typeof code === "string" && KNOWN.has(code);
}

/** Text of an error: `examTemplates.errors.<code>` for template codes, else the shared LMS/org wording. */
export function useExamTemplateErrorText() {
  const { t } = useTranslation();
  return useCallback((error: unknown): string => {
    const e = error as { code?: string; details?: unknown } | null;
    const code = e?.code;
    if (code === "template_locked" && (e?.details as { source?: string } | undefined)?.source === "exam_template") {
      return t("examTemplates.errors.template_locked_exam");
    }
    if (code && KNOWN.has(code)) return t(`examTemplates.errors.${code}`);
    return apiErrorText(t, error);
  }, [t]);
}

export function ExamTemplateError({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  const text = useExamTemplateErrorText();
  if (!error) return null;
  return <ErrorState variant="inline" message={text(error)} onRetry={onRetry} className={className} />;
}

/** `spec_invalid` details as a list (`[{loc, msg, type, limit}]`, possibly wrapped in `{errors|issues}`). */
export function specIssuesOf(error: unknown): SpecIssue[] {
  const d = (error as { details?: unknown } | null)?.details;
  const raw = Array.isArray(d) ? d : d && typeof d === "object"
    ? ((d as { errors?: unknown; issues?: unknown }).errors ?? (d as { issues?: unknown }).issues) : null;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x): x is { loc?: unknown; msg?: unknown; type?: unknown; limit?: unknown; truncated?: unknown } => !!x && typeof x === "object")
    .map((x) => ({
      loc: Array.isArray(x.loc) ? (x.loc as (string | number)[]) : [],
      msg: typeof x.msg === "string" ? x.msg : "",
      type: typeof x.type === "string" ? x.type : undefined,
      limit: typeof x.limit === "number" ? x.limit : typeof x.truncated === "number" ? x.truncated : undefined,
    }));
}

// --- Phase 7b S7: spec issues in the user's language (by error type; the server's English `msg` is never shown) ---
const ISSUE_TYPES: Record<string, string> = {
  missing: "missing", extra_forbidden: "extra_forbidden", too_long: "too_long", string_too_long: "string_too_long",
  too_short: "too_short", string_too_short: "string_too_short", greater_than_equal: "greater_than_equal",
  greater_than: "greater_than", less_than_equal: "less_than_equal", less_than: "less_than", literal_error: "literal_error",
  enum: "literal_error", string_pattern_mismatch: "string_pattern_mismatch", int_type: "int_type", int_parsing: "int_type",
  int_from_float: "int_type", bool_type: "bool_type", bool_parsing: "bool_type", string_type: "type", list_type: "type",
  dict_type: "type", model_type: "type", model_attributes_type: "type", uuid_parsing: "uuid", uuid_type: "uuid",
  value_error: "value_error", assertion_error: "value_error", duplicate_key: "duplicate_key",
  timer_needs_forward_only: "timer_needs_forward_only", section_times_exceed_total: "section_times_exceed_total",
  min_exceeds_max: "min_exceeds_max", positive_int: "positive_int", invalid_types: "invalid_types",
  invalid_rule: "invalid_rule", binds_missing_section: "binds_missing_section", binds_taken: "binds_taken",
  bound_key_must_be_empty: "bound_key_must_be_empty", options_collide: "options_collide", unknown_scheme: "unknown_scheme",
  not_shareable: "not_shareable", reserved: "reserved", truncated: "truncated",
  // Phase 8b S4: client pre-check types (specDraft.precheckDraft)
  types_required: "types_required", sections_required: "sections_required", title_required: "title_required",
};
const RANGE = new Set(["greater_than_equal", "greater_than", "less_than_equal", "less_than"]);
export const SECTION_FIELDS: Record<string, string> = {
  key: "examTemplates.specForm.key", title: "examTemplates.specForm.sectionTitle", instructions: "examTemplates.specForm.instructions",
  time_limit_s: "examTemplates.specForm.timeLimit", min_items: "examTemplates.specForm.minItems", max_items: "examTemplates.specForm.maxItems",
  allowed_types: "examTemplates.specForm.types", allow_passages: "examTemplates.specForm.allowPassages",
  passage_display: "examTemplates.specForm.passageDisplay",
};
export const DEFAULT_FIELDS: Record<string, string> = {
  time_limit_s: "examTemplates.specForm.totalTime", allowed_attempts: "assessments.settings.attempts",
  score_policy: "assessments.settings.scorePolicy", results_policy: "assessments.settings.resultsPolicy",
  show_correct_answers: "assessments.settings.showCorrect", shuffle_items: "assessments.settings.shuffleItems",
  shuffle_choices: "assessments.settings.shuffleChoices",
};
export const PARAM_FIELDS: Record<string, string> = {
  key: "examTemplates.specForm.paramKey", options: "examTemplates.specForm.paramOptions", binds: "examTemplates.specForm.paramSection",
  kind: "examTemplates.specForm.paramKind",
};
export const TOP_FIELDS: Record<string, string> = {
  title: "examTemplates.fields.title", description: "examTemplates.fields.description",
  sections: "examTemplates.specForm.sections", defaults: "examTemplates.specForm.defaults", parameters: "examTemplates.specForm.parameters",
  lock_scope: "examTemplates.specForm.lockScope", navigation: "examTemplates.editor.navigation", display_mode: "examTemplates.editor.displayMode",
  passage_display: "examTemplates.editor.passageDisplay", result_view: "examTemplates.editor.resultView", scoring: "examTemplates.editor.scheme",
  importer_profile: "examTemplates.specForm.importerProfile", schema: "examTemplates.specForm.schema",
};
const isIndex = (x: unknown) => x !== undefined && /^\d+$/.test(String(x));

/** Does `loc` start with `prefix` (indexes compared as text: pydantic sends "0", the cross checks 0)? */
export function locStartsWith(loc: (string | number)[], prefix: (string | number)[]): boolean {
  return prefix.every((p, i) => String(loc[i]) === String(p));
}

/** `where(issue.loc)`: "Раздел «Теория» › Не больше вопросов"; `what(issue)`: the translated message. */
export function useSpecIssueText(sectionName: (index: number) => string) {
  const { t } = useTranslation();
  const where = useCallback((loc: (string | number)[]): string => {
    const [a, b, c] = loc.map(String);
    if (a === undefined) return t("examTemplates.specForm.template");
    const parts: string[] = [];
    const label = (map: Record<string, string>, k: string | undefined) => { if (k !== undefined) parts.push(map[k] ? t(map[k]) : k); };
    if (a === "sections" && isIndex(b)) { parts.push(sectionName(Number(b))); label(SECTION_FIELDS, c); }
    else if (a === "parameters" && isIndex(b)) { parts.push(t("examTemplates.specForm.paramN", { n: Number(b) + 1 })); label(PARAM_FIELDS, c); }
    else if (a === "defaults") { parts.push(t(TOP_FIELDS.defaults)); label(DEFAULT_FIELDS, b); }
    else { label(TOP_FIELDS, a); }
    return parts.join(" › ");
  }, [t, sectionName]);
  const what = useCallback((issue: SpecIssue): string => {
    const key = ISSUE_TYPES[issue.type ?? ""];
    if (!key) return t("examTemplates.specIssues.generic");
    const last = String(issue.loc[issue.loc.length - 1] ?? "");
    if (RANGE.has(key) && last === "time_limit_s" && issue.limit !== undefined) {
      const minutes = Math.round((issue.limit / 60) * 100) / 100;
      return t(key.startsWith("greater") ? "examTemplates.specIssues.minutesMin" : "examTemplates.specIssues.minutesMax", { limit: minutes });
    }
    if (key === "duplicate_key" && String(issue.loc[0]) === "parameters") return t("examTemplates.specIssues.duplicate_param");
    if ((RANGE.has(key) || key.startsWith("too_") || key.startsWith("string_too") || key === "truncated") && issue.limit === undefined) {
      return t("examTemplates.specIssues.generic");
    }
    return t(`examTemplates.specIssues.${key}`, { limit: issue.limit ?? "" });
  }, [t]);
  return { where, what };
}
// --- Phase 7b S7 end ---

const SCOPE_TONE: Record<ExamTemplateScope, BadgeTone> = { platform: "system", organization: "info", teacher: "neutral" };
export function ScopeBadge({ scope, ownerId }: { scope: ExamTemplateScope; ownerId?: string | null }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  // Phase 8b S5: a teacher template seen by someone else (the org admin) is "Teacher's", not "Mine"
  const other = scope === "teacher" && !!ownerId && !!user?.uid && ownerId !== user.uid;
  return <Badge tone={SCOPE_TONE[scope] ?? "neutral"}>{other ? t("examTemplates.scopeTeacherOther") : t(`examTemplates.scope.${scope}`)}</Badge>;
}

const STATUS_TONE: Record<ExamTemplateStatus, BadgeTone> = { draft: "warning", published: "success", archived: "neutral" };
export function TemplateStatusBadge({ status }: { status: ExamTemplateStatus }) {
  const { t } = useTranslation();
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{t(`examTemplates.status.${status}`)}</Badge>;
}

export function LockedBadge() {
  const { t } = useTranslation();
  return <Badge tone="neutral" icon={<Lock className="h-3.5 w-3.5" aria-hidden="true" />}>{t("examTemplates.locked")}</Badge>;
}

/** Where a template management page lives: teacher (mine), organization admin, platform admin. */
export type TemplateArea = { kind: "teacher" } | { kind: "org"; orgId: string; readOnly?: boolean } | { kind: "platform" };
