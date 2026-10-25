"use client";

import React from "react";
import { ChevronDown } from "lucide-react";
import { FieldError, FieldHint, FieldLabel, useFieldIds, type FieldProps } from "./Field";
import { cn, fieldBase, fieldBorder } from "./utils";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "size">, FieldProps {
  /** Options; alternatively pass `<option>` children. */
  options?: SelectOption[];
  /** First empty option ("Choose ..."), value "". */
  placeholder?: string;
}

/** Native select (works with every screen reader and phone picker). */
export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, optional, containerClassName, options, placeholder, id, className, children, "aria-describedby": extra, ...rest },
  ref,
) {
  const ids = useFieldIds(id, hint, error, extra);
  return (
    <div className={containerClassName}>
      <FieldLabel htmlFor={ids.id} optional={optional}>{label}</FieldLabel>
      <div className="relative mt-1">
        <select
          ref={ref}
          id={ids.id}
          aria-invalid={error ? true : undefined}
          aria-describedby={ids.describedBy}
          className={cn(fieldBase, fieldBorder(!!error), "min-h-11 appearance-none py-2 pr-10", className)}
          {...rest}
        >
          {placeholder !== undefined && <option value="">{placeholder}</option>}
          {options?.map((o) => (
            <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
          ))}
          {children}
        </select>
        <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
      </div>
      <FieldError id={ids.errorId}>{error}</FieldError>
      <FieldHint id={ids.hintId}>{hint}</FieldHint>
    </div>
  );
});
