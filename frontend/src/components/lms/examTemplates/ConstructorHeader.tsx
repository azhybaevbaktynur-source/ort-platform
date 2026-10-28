"use client";

// Phase 8b S4: constructor header (PHASE_8B_DESIGN 9.1): name, scope / status / lock badges, "v3 · N unpublished
// changes", the autosave status, Publish, Preview and the More menu (archive, lock / unlock, promote, import format).
import React from "react";
import { AlertCircle, Check, CloudOff, Eye, Loader2, PencilLine } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { ExamTemplateOut } from "@/lib/lms/examTemplateTypes";
import { Button, MenuButton, PageHeader, cn, type Breadcrumb, type MenuItem } from "@/components/ui";
import { LockedBadge, ScopeBadge, TemplateStatusBadge } from "./ui";
import type { SaveState } from "./useConstructor";

export type HeaderAction = "publish" | "archive" | "lock" | "unlock" | "promote" | "importFormat";

export function ConstructorHeader({ tpl, name, crumbs, readOnly, saveState, issueCount, canPublish, onAction, onPreview, onRetrySave }: {
  tpl: ExamTemplateOut;
  name: string;
  crumbs: Breadcrumb[];
  readOnly: boolean;
  saveState: SaveState;
  issueCount: number;
  canPublish: boolean;
  onAction: (a: HeaderAction) => void;
  onPreview: () => void;
  onRetrySave: () => void;
}) {
  const { t } = useTranslation();
  const archived = tpl.status === "archived";
  const menu: MenuItem[] = [
    ...(tpl.current_version_no != null ? [{ id: "importFormat", label: t("examTemplates.importFormat.download"), description: t("examTemplates.constructor.header.importFormatHint", { n: tpl.current_version_no }) }] : []),
    ...(tpl.can_lock && !tpl.locked && !archived ? [{ id: "lock", label: t("examTemplates.lock.action"), description: t("examTemplates.lock.menuHint") }] : []),
    ...(tpl.can_lock && tpl.locked && !archived ? [{ id: "unlock", label: t("examTemplates.unlock.action"), description: t("examTemplates.unlock.menuHint") }] : []),
    ...(tpl.can_promote && !archived ? [{ id: "promote", label: t("examTemplates.promote.action"), description: t("examTemplates.promote.menuHint") }] : []),
    ...(!archived ? [{ id: "archive", label: t("examTemplates.archive.action"), description: t("examTemplates.archive.menuHint") }] : []),
  ];
  const changes = tpl.unpublished_changes;
  const version = tpl.current_version_no != null
    ? [t("examTemplates.versionShort", { n: tpl.current_version_no }), changes ? t("examTemplates.constructor.header.unpublished", { n: changes }) : null].filter(Boolean).join(" · ")
    : t("examTemplates.editor.noVersion");

  return (
    <PageHeader
      title={name}
      breadcrumbs={crumbs}
      badge={<span className="inline-flex flex-wrap gap-1.5"><ScopeBadge scope={tpl.owner_scope} /><TemplateStatusBadge status={tpl.status} />{tpl.locked && <LockedBadge />}</span>}
      description={(
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>{version}</span>
          {!readOnly && <SaveStatus state={saveState} issueCount={issueCount} onRetry={onRetrySave} />}
        </span>
      )}
      primaryAction={readOnly ? undefined : (
        <Button disabled={!canPublish} onClick={() => onAction("publish")}>{t("examTemplates.publish.action")}</Button>
      )}
      secondaryActions={(
        <>
          {!archived && (
            <Button variant="secondary" leftIcon={<Eye className="h-4 w-4" aria-hidden="true" />} onClick={onPreview}>
              {t("examTemplates.constructor.header.preview")}
            </Button>
          )}
          {menu.length > 0 && (
            <MenuButton label={t("examTemplates.editor.more")} items={menu} variant="secondary" align="end" onSelect={(id) => onAction(id as HeaderAction)} />
          )}
        </>
      )}
    />
  );
}

/** Autosave state in words (and an icon); polite live region so screen readers hear "Saved" / "Not saved". */
export function SaveStatus({ state, issueCount, onRetry }: { state: SaveState; issueCount: number; onRetry: () => void }) {
  const { t } = useTranslation();
  const icon = {
    idle: null,
    dirty: <PencilLine className="h-4 w-4" aria-hidden="true" />,
    saving: <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />,
    saved: <Check className="h-4 w-4" aria-hidden="true" />,
    invalid: <AlertCircle className="h-4 w-4" aria-hidden="true" />,
    conflict: <AlertCircle className="h-4 w-4" aria-hidden="true" />,
    error: <CloudOff className="h-4 w-4" aria-hidden="true" />,
  }[state];
  const tone = state === "invalid" || state === "conflict" || state === "error" ? "text-danger-700"
    : state === "saved" ? "text-success-700" : "text-slate-600";
  return (
    <span role="status" aria-live="polite" className={cn("inline-flex items-center gap-1.5 text-sm font-medium", tone)}>
      {icon}
      {state !== "idle" && (state === "invalid"
        ? t("examTemplates.constructor.saveState.invalid", { n: issueCount })
        : t(`examTemplates.constructor.saveState.${state}`))}
      {(state === "error" || state === "conflict") && (
        <Button variant="link" size="sm" className="px-1" onClick={onRetry}>
          {t(state === "error" ? "examTemplates.constructor.saveState.retry" : "examTemplates.constructor.saveState.resolve")}
        </Button>
      )}
    </span>
  );
}
