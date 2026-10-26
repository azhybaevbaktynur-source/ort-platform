"use client";

// Phase 7b S4: shared bits of the exam template screens (errors, badges, labels).
import React, { useCallback } from "react";
import { Lock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
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

/** `spec_invalid` details as a list (`[{loc, msg}]`, possibly wrapped in `{errors|issues}`). */
export function specIssuesOf(error: unknown): SpecIssue[] {
  const d = (error as { details?: unknown } | null)?.details;
  const raw = Array.isArray(d) ? d : d && typeof d === "object"
    ? ((d as { errors?: unknown; issues?: unknown }).errors ?? (d as { issues?: unknown }).issues) : null;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x): x is { loc?: unknown; msg?: unknown } => !!x && typeof x === "object")
    .map((x) => ({ loc: Array.isArray(x.loc) ? (x.loc as (string | number)[]) : [], msg: typeof x.msg === "string" ? x.msg : "" }));
}

/** "sections › 0 › max_items" */
export function locText(loc: (string | number)[]): string {
  return loc.length ? loc.join(" › ") : "—";
}

const SCOPE_TONE: Record<ExamTemplateScope, BadgeTone> = { platform: "system", organization: "info", teacher: "neutral" };
export function ScopeBadge({ scope }: { scope: ExamTemplateScope }) {
  const { t } = useTranslation();
  return <Badge tone={SCOPE_TONE[scope] ?? "neutral"}>{t(`examTemplates.scope.${scope}`)}</Badge>;
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
