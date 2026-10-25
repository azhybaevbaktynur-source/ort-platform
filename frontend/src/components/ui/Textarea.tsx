"use client";

import React from "react";
import { FieldError, FieldHint, FieldLabel, useFieldIds, type FieldProps } from "./Field";
import { cn, fieldBase, fieldBorder } from "./utils";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement>, FieldProps {}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, optional, containerClassName, id, className, rows = 3, "aria-describedby": extra, ...rest },
  ref,
) {
  const ids = useFieldIds(id, hint, error, extra);
  return (
    <div className={containerClassName}>
      <FieldLabel htmlFor={ids.id} optional={optional}>{label}</FieldLabel>
      <textarea
        ref={ref}
        id={ids.id}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={ids.describedBy}
        className={cn(fieldBase, fieldBorder(!!error), "mt-1 py-2.5", className)}
        {...rest}
      />
      <FieldError id={ids.errorId}>{error}</FieldError>
      <FieldHint id={ids.hintId}>{hint}</FieldHint>
    </div>
  );
});
