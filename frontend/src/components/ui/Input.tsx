"use client";

import React from "react";
import { FieldError, FieldHint, FieldLabel, useFieldIds, type FieldProps } from "./Field";
import { cn, fieldBase, fieldBorder } from "./utils";

export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "size">, FieldProps {
  /** Icon or text inside the field on the left (decorative). */
  leading?: React.ReactNode;
  /** Element inside the field on the right (for example a clear button). */
  trailing?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, optional, containerClassName, leading, trailing, id, className, "aria-describedby": extra, ...rest },
  ref,
) {
  const ids = useFieldIds(id, hint, error, extra);
  return (
    <div className={containerClassName}>
      <FieldLabel htmlFor={ids.id} optional={optional}>{label}</FieldLabel>
      <div className="relative mt-1">
        {leading && (
          <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-500">{leading}</span>
        )}
        <input
          ref={ref}
          id={ids.id}
          aria-invalid={error ? true : undefined}
          aria-describedby={ids.describedBy}
          className={cn(fieldBase, fieldBorder(!!error), "min-h-11 py-2", !!leading && "pl-10", !!trailing && "pr-12", className)}
          {...rest}
        />
        {trailing && <span className="absolute inset-y-0 right-0 flex items-center">{trailing}</span>}
      </div>
      <FieldError id={ids.errorId}>{error}</FieldError>
      <FieldHint id={ids.hintId}>{hint}</FieldHint>
    </div>
  );
});
