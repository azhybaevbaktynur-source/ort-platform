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
}

/** On/off switch (`role="switch"`), label on the left, the whole row is a 44 px tap target. */
export function Switch({ label, hint, error, containerClassName, checked, onChange, id, disabled = false, busy = false, name }: SwitchProps) {
  const ids = useFieldIds(id, hint, error);
  const labelId = `${ids.id}-label`;
  const off = disabled || busy;
  return (
    <div className={containerClassName}>
      <div className="flex min-h-11 items-center justify-between gap-4 py-1.5">
        <label id={labelId} htmlFor={ids.id}
          className={cn("text-base leading-6 text-slate-800 sm:text-sm sm:leading-6", off ? "cursor-not-allowed" : "cursor-pointer", disabled && "text-slate-600")}>
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
          className={cn("group inline-flex h-11 w-14 shrink-0 items-center justify-center rounded-full disabled:cursor-not-allowed disabled:opacity-60", focusRing)}
        >
          <span
            aria-hidden="true"
            className={cn(
              "relative inline-flex h-7 w-12 items-center rounded-full border-2 transition-colors",
              checked ? "border-brand-600 bg-brand-600" : "border-slate-400 bg-slate-200",
              busy && "opacity-70",
            )}
          >
            <span className={cn("h-5 w-5 rounded-full bg-white shadow transition-transform", checked ? "translate-x-[22px]" : "translate-x-0.5")} />
          </span>
        </button>
      </div>
      <FieldError id={ids.errorId}>{error}</FieldError>
      <FieldHint id={ids.hintId}>{hint}</FieldHint>
    </div>
  );
}
