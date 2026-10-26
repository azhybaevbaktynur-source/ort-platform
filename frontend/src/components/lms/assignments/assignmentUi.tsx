"use client";

// Phase 7a S5: small shared pieces of the assignment screens: kind icon and badge, the student status badge,
// error text for the new error codes, number parsing and the late/size formatting.
import React, { useCallback } from "react";
import { CheckCircle2, Circle, Clock, FileText, ListChecks, MinusCircle, PlayCircle, Star, Upload, UserCheck, CircleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { ASSIGNMENT_ERROR_CODES, type AssignmentKind, type AssignmentStudentStatus } from "@/lib/lms/assignmentTypes";
import { Badge, ErrorState, type BadgeTone } from "@/components/ui";
import { useErrorText } from "@/components/lms/home/useErrorText";

const KIND_ICON: Record<AssignmentKind, React.ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" }>> = {
  quiz: ListChecks,
  text: FileText,
  file: Upload,
  none: UserCheck,
};

/** Decorative icon of an assignment kind (always next to its text). */
export function KindIcon({ kind, className = "h-4 w-4" }: { kind: AssignmentKind; className?: string }) {
  const Icon = KIND_ICON[kind] ?? FileText;
  return <Icon aria-hidden="true" className={`${className} shrink-0`} />;
}

export function KindBadge({ kind, ort = false }: { kind: AssignmentKind; ort?: boolean }) {
  const { t } = useTranslation();
  return (
    <Badge tone={kind === "quiz" ? "info" : "neutral"} icon={<KindIcon kind={kind} />}>
      {kind === "quiz" && ort ? t("assignments.kinds.ortExam") : t(`assignments.kinds.${kind}`)}
    </Badge>
  );
}

const STATUS: Record<AssignmentStudentStatus, { tone: BadgeTone; icon: React.ReactNode }> = {
  not_started: { tone: "neutral", icon: <Circle aria-hidden="true" /> },
  in_progress: { tone: "info", icon: <PlayCircle aria-hidden="true" /> },
  submitted: { tone: "info", icon: <CheckCircle2 aria-hidden="true" /> },
  graded: { tone: "success", icon: <Star aria-hidden="true" /> },
  missing: { tone: "danger", icon: <CircleAlert aria-hidden="true" /> },
  excused: { tone: "neutral", icon: <MinusCircle aria-hidden="true" /> },
};

export function AssignmentStatusBadge({ status }: { status: AssignmentStudentStatus }) {
  const { t } = useTranslation();
  const s = STATUS[status] ?? STATUS.not_started;
  return <Badge tone={s.tone} icon={s.icon}>{t(`assignments.status.${status}`)}</Badge>;
}

export function LateBadge() {
  const { t } = useTranslation();
  return <Badge tone="warning" icon={<Clock aria-hidden="true" />}>{t("assignments.late")}</Badge>;
}

const KNOWN = new Set<string>(ASSIGNMENT_ERROR_CODES);

/** What happened and what to do for the Phase 7a codes; anything else falls back to the shared texts. */
export function useAssignmentErrorText() {
  const { t } = useTranslation();
  const fallback = useErrorText();
  return useCallback((error: unknown): string => {
    const e = error as { code?: string; details?: Record<string, unknown> } | null;
    const code = e?.code;
    if (code === "rate_limited" && typeof e?.details?.retry_after_seconds === "number") {
      return t("assignments.errors.rate_limited_wait", { seconds: e.details.retry_after_seconds as number });
    }
    // Phase 7a UX: a locked ORT course refuses non-quiz assignments (details.field = "kind")
    if (code === "template_locked" && e?.details?.field === "kind") return t("assignments.errors.template_locked_kind");
    if (code && KNOWN.has(code) && code !== "network") return t(`assignments.errors.${code}`);
    return fallback(error);
  }, [t, fallback]);
}

/** Inline error with an optional Retry (design-system ErrorState). */
export function AssignmentError({ error, onRetry, title, className }: { error: unknown; onRetry?: () => void; title?: string; className?: string }) {
  const text = useAssignmentErrorText();
  if (!error) return null;
  return <ErrorState variant="inline" title={title} message={text(error)} onRetry={onRetry} className={className} />;
}

/** "12.5" / "12,5" -> 12.5; empty -> null; invalid -> NaN. */
export function parsePoints(s: string): number | null {
  const v = s.trim().replace(",", ".");
  if (!v) return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.round(n * 100) / 100 : Number.NaN;
}

export function fmtBytes(n: number | null | undefined, t: (k: string, p?: Record<string, string | number>) => string): string {
  if (!n || n <= 0) return "";
  if (n < 1024 * 1024) return t("assignments.size.kb", { n: Math.max(1, Math.round(n / 1024)) });
  return t("assignments.size.mb", { n: Math.round((n / (1024 * 1024)) * 10) / 10 });
}

/** Points shown without trailing zeros. */
export function fmtPts(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v);
  return Number.isFinite(n) ? String(Math.round(n * 100) / 100) : String(v);
}
