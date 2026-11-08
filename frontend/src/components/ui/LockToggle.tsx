"use client";

import React, { useId } from "react";
import { Lock, LockOpen } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { Spinner } from "./Spinner";
import { cn, focusRing } from "./utils";

export interface LockToggleProps {
  /** On: locked (Pro, only for students with access). Off: open to everyone. */
  locked: boolean;
  /** Called on a click; the caller saves and flips `locked`. */
  onToggle: () => void;
  /** Accessible name, stable across states (the state is `aria-pressed`), e.g. "Pro module: {title}". Default "Pro". */
  label?: string;
  /** Tooltip and description while locked (default `ui.pro.locked`: "... Click to open it to everyone."). */
  lockedHint?: string;
  /** Tooltip and description while open (default `ui.pro.unlocked`: "... Click to make it Pro."). */
  unlockedHint?: string;
  /** A change is being saved: blocks clicks, shows a spinner, sets `aria-busy`. */
  busy?: boolean;
  disabled?: boolean;
  className?: string;
}

/**
 * FB8 S0 (STAFF_UX_AUDIT §1): a 44 px icon toggle for Pro (paid) vs free on a row (modules, items): `Lock` in gold
 * when locked, `LockOpen` in slate when open. A toggle button (`aria-pressed`); the tooltip (`title`) says the state
 * and what a click does, and is also its `aria-describedby` text. Use it where a full `Switch` row would be too heavy.
 */
export function LockToggle({ locked, onToggle, label, lockedHint, unlockedHint, busy = false, disabled = false, className }: LockToggleProps) {
  const { t } = useTranslation();
  const hintId = useId();
  const hint = locked ? (lockedHint ?? t("ui.pro.locked")) : (unlockedHint ?? t("ui.pro.unlocked"));
  const Icon = locked ? Lock : LockOpen;
  return (
    <button type="button" aria-pressed={locked} aria-label={label ?? t("ui.pro.label")} aria-describedby={hintId} title={hint}
      aria-busy={busy || undefined} disabled={disabled || busy} onClick={() => { if (!busy) onToggle(); }}
      className={cn(
        "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        locked
          ? "border-gold-300 bg-gold-50 text-gold-700 hover:bg-gold-100"
          : "border-transparent text-slate-500 hover:bg-slate-100 hover:text-slate-700",
        focusRing, className,
      )}>
      {busy ? <Spinner className="h-5 w-5" /> : <Icon aria-hidden="true" className="h-5 w-5" />}
      <span id={hintId} className="sr-only">{hint}</span>
    </button>
  );
}
