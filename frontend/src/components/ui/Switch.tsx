"use client";

import React from "react";
import { FieldError, FieldHint, useFieldIds, type FieldProps } from "./Field";
import { cn, focusRing } from "./utils";

export interface SwitchProps extends Omit<FieldProps, "optional"> {
  checked: boolean;
  onChange: (checked: boolean) => void;
  id?: string;
  disabled?: boolean;
  /** Spinner-free busy state while a change is saved: blocks toggling and sets `aria-busy`. */
  busy?: boolean;
  name?: string;
  /** `md` (default): 28 × 48 px track in a 44 px row. `sm`: 20 × 36 px track, no row padding (toggles inside list rows). */
  size?: "md" | "sm";
  /** Keep the label for screen readers only (`sr-only`), e.g. "Published: {title}" on a row whose title is visible. */
  hideLabel?: boolean;
}

/**
 * On/off switch (`role="switch"`) for a setting that applies at once: label on the left, the whole row is a 44 px
 * tap target. In list rows use `size="sm" hideLabel` (the label still names the switch for screen readers).
 */
export function Switch({
  label, hint, error, containerClassName, checked, onChange, id, disabled = false, busy = false, name, size = "md", hideLabel = false,
}: SwitchProps) {
  const ids = useFieldIds(id, hint, error);
  const labelId = `${ids.id}-label`;
  const off = disabled || busy;
  const sm = size === "sm";
  return (
    <div className={containerClassName}>
      <div className={cn(
        "flex items-center",
        hideLabel ? "justify-end" : sm ? "justify-between gap-3" : "justify-between gap-4",
        !sm && "min-h-11 py-1.5",
      )}>
        <label id={labelId} htmlFor={ids.id}
          className={cn(
            hideLabel ? "sr-only" : sm ? "text-sm leading-5 text-slate-800" : "text-base leading-6 text-slate-800 sm:text-sm sm:leading-6",
            off ? "cursor-not-allowed" : "cursor-pointer", disabled && "text-slate-600",
          )}>
          {label}
        </label>
        <button
          id={ids.id}
          type="button"
          role="switch"
          name={name}
          aria-checked={checked}
          aria-labelledby={labelId}
          aria-describedby={ids.describedBy}
          aria-invalid={error ? true : undefined}
          aria-busy={busy || undefined}
          disabled={disabled}
          onClick={() => { if (!busy) onChange(!checked); }}
          className={cn(
            "group inline-flex shrink-0 items-center justify-center rounded-full disabled:cursor-not-allowed disabled:opacity-60",
            // sm keeps a 44 px target on phones and is a 32 px one from `sm`
            sm ? "h-11 w-11 sm:h-8 sm:w-11" : "h-11 w-14",
            focusRing,
          )}
        >
          <span
            aria-hidden="true"
            className={cn(
              "relative inline-flex items-center rounded-full border-2 transition-colors",
              sm ? "h-5 w-9" : "h-7 w-12",
              checked ? "border-brand-600 bg-brand-600" : "border-slate-400 bg-slate-200",
              busy && "opacity-70",
            )}
          >
            {sm ? (
              <span className={cn("h-3 w-3 rounded-full bg-white shadow transition-transform", checked ? "translate-x-[18px]" : "translate-x-0.5")} />
            ) : (
              <span className={cn("h-5 w-5 rounded-full bg-white shadow transition-transform", checked ? "translate-x-[22px]" : "translate-x-0.5")} />
            )}
          </span>
        </button>
      </div>
      <FieldError id={ids.errorId}>{error}</FieldError>
      <FieldHint id={ids.hintId}>{hint}</FieldHint>
    </div>
  );
}
