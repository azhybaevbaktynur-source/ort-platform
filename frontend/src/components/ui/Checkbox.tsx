"use client";

import React from "react";
import { FieldError, FieldHint, useFieldIds, type FieldProps } from "./Field";
import { cn } from "./utils";

export interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type" | "size">, Omit<FieldProps, "optional"> {}

/** Checkbox with its label to the right; the whole row is a 44 px tap target. */
export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, hint, error, containerClassName, id, className, disabled, "aria-describedby": extra, ...rest },
  ref,
) {
  const ids = useFieldIds(id, hint, error, extra);
  return (
    <div className={containerClassName}>
      <label htmlFor={ids.id} className={cn("flex min-h-11 items-start gap-3 py-2.5", disabled ? "cursor-not-allowed" : "cursor-pointer")}>
        <input
          ref={ref}
          id={ids.id}
          type="checkbox"
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={ids.describedBy}
          className={cn(
            "mt-0.5 h-5 w-5 shrink-0 cursor-pointer rounded border-slate-400 accent-brand-600",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2",
            "disabled:cursor-not-allowed disabled:opacity-60",
            !!error && "outline outline-2 outline-offset-1 outline-danger-600",
            className,
          )}
          {...rest}
        />
        <span className={cn("text-base leading-6 text-slate-800 sm:text-sm sm:leading-6", disabled && "text-slate-600")}>{label}</span>
      </label>
      {(error || hint) && (
        <div className="-mt-1.5 pl-8">
          <FieldError id={ids.errorId}>{error}</FieldError>
          <FieldHint id={ids.hintId}>{hint}</FieldHint>
        </div>
      )}
    </div>
  );
});
