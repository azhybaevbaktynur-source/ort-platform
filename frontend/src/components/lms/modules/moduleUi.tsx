"use client";

// Phase 8a S4a: small shared pieces of the module screens: kind icons, the module state badge, requirement and
// lock-reason texts in plain words, error texts and where a student item leads.
import React, { useCallback } from "react";
import { CheckCircle2, Circle, ExternalLink, FileText, Heading, Link2, ListChecks, Lock, PlayCircle, Upload, UserCheck, File as FileIcon } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import type { AssignmentKind } from "@/lib/lms/assignmentTypes";
import { MODULE_ERROR_CODES, type ItemKind, type ItemLinkOut, type LockReasonOut, type ModuleState, type RequirementType } from "@/lib/lms/modulesTypes";
import { Badge, type BadgeTone } from "@/components/ui";
import { useAssignmentErrorText } from "@/components/lms/assignments/assignmentUi";
import { fmtShortDateTime } from "@/components/lms/home/format";

type IconT = React.ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" }>;
const ITEM_ICON: Record<ItemKind, IconT> = { page: FileText, file: FileIcon, assignment: ListChecks, url: Link2, header: Heading };
const ASSIGNMENT_ICON: Record<AssignmentKind, IconT> = { quiz: ListChecks, text: FileText, file: Upload, none: UserCheck };

/** Decorative icon of an item kind (always next to its text). */
export function ItemKindIcon({ kind, assignmentKind, className = "h-4 w-4" }: { kind: ItemKind; assignmentKind?: AssignmentKind | null; className?: string }) {
  const Icon = kind === "assignment" && assignmentKind ? ASSIGNMENT_ICON[assignmentKind] ?? ListChecks : ITEM_ICON[kind] ?? FileText;
  return <Icon aria-hidden="true" className={`${className} shrink-0`} />;
}

/** "Page", "File", "Quiz", "Text answer", "Link", "Header". */
export function useItemKindText() {
  const { t } = useTranslation();
  return useCallback((kind: ItemKind, assignmentKind?: AssignmentKind | null) => (
    kind === "assignment" && assignmentKind ? t(`assignments.kinds.${assignmentKind}`) : t(`modules.kinds.${kind}`)
  ), [t]);
}

export function ExternalIcon() {
  return <ExternalLink aria-hidden="true" className="h-4 w-4 shrink-0" />;
}

const STATE: Record<ModuleState, { tone: BadgeTone; icon: React.ReactNode }> = {
  locked: { tone: "neutral", icon: <Lock aria-hidden="true" /> },
  unlocked: { tone: "neutral", icon: <Circle aria-hidden="true" /> },
  started: { tone: "info", icon: <PlayCircle aria-hidden="true" /> },
  completed: { tone: "success", icon: <CheckCircle2 aria-hidden="true" /> },
};

export function ModuleStateBadge({ state }: { state: ModuleState }) {
  const { t } = useTranslation();
  const s = STATE[state] ?? STATE.unlocked;
  return <Badge tone={s.tone} icon={s.icon}>{t(`modules.state.${state}`)}</Badge>;
}

/** Thresholds come as numbers (or decimal strings); "80" and "12.5" without trailing zeros. */
export function fmtThreshold(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? String(Math.round(n * 100) / 100) : String(v);
}

/** What the student must do: "View", "Mark as done", "Hand in", "Score at least 80 %". */
export function useRequirementText() {
  const { t } = useTranslation();
  return useCallback((type: RequirementType, threshold?: number | null) => (
    t(`modules.req.${type}`, { threshold: fmtThreshold(threshold) })
  ), [t]);
}

/** Lock reasons in plain words: "Opens 12/11/2026, 09:00", "Finish “Module 1” first". */
export function useLockReasonText() {
  const { lang, t } = useTranslation();
  return useCallback((r: LockReasonOut, defaultLang?: Lang) => {
    const title = pickLocalized(r.title as LocalizedText | null | undefined, lang, defaultLang) || t("modules.untitledModule");
    if (r.kind === "unlock_at") return t("modules.reason.unlockAt", { date: fmtShortDateTime(r.at, lang) });
    if (r.kind === "prerequisite") return t("modules.reason.prerequisite", { title });
    return t("modules.reason.sequential", { title });
  }, [lang, t]);
}

const KNOWN = new Set<string>(MODULE_ERROR_CODES);

/** Module error codes first (`modules.errors.*`), then the assignment and shared texts. */
export function useModuleErrorText() {
  const { t } = useTranslation();
  const fallback = useAssignmentErrorText();
  return useCallback((error: unknown): string => {
    const code = (error as { code?: string } | null)?.code;
    if (code && KNOWN.has(code)) return t(`modules.errors.${code}`);
    return fallback(error);
  }, [t, fallback]);
}

/** In-app target of a student item (null: url, header, file; those are handled by the caller). */
export function itemHref(base: string, kind: ItemKind, link: ItemLinkOut | null | undefined): string | null {
  if (!link) return null;
  if (kind === "page" && link.page_id) return `${base}/pages/${link.page_id}`;
  if (kind === "assignment") {
    if (link.assignment_kind === "quiz" && link.assessment_id) return `${base}/assessments/${link.assessment_id}`;
    if (link.assignment_id) return `${base}/assignments/${link.assignment_id}`;
  }
  return null;
}
