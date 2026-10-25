"use client";

import React, { useId } from "react";
import { CircleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { cn } from "./utils";

/** Props shared by every form control: a visible label, optional hint and error. */
export interface FieldProps {
  /** Visible label (required: every input has a visible label). */
  label: React.ReactNode;
  /** Help text under the control, linked with `aria-describedby`. */
  hint?: React.ReactNode;
  /** Error text; sets `aria-invalid` and is linked with `aria-describedby`. */
  error?: React.ReactNode;
  /** Shows "(optional)" after the label. */
  optional?: boolean;
  /** Class of the wrapper element. */
  containerClassName?: string;
}

export interface FieldIds {
  id: string;
  hintId?: string;
  errorId?: string;
  describedBy?: string;
}

/** Ids for a control: its own id (or a generated one) and the hint/error ids. */
export function useFieldIds(id: string | undefined, hint: unknown, error: unknown, extraDescribedBy?: string): FieldIds {
  const auto = useId();
  const base = id ?? `f${auto.replace(/:/g, "")}`;
  const hintId = hint ? `${base}-hint` : undefined;
  const errorId = error ? `${base}-error` : undefined;
  const describedBy = [extraDescribedBy, errorId, hintId].filter(Boolean).join(" ") || undefined;
  return { id: base, hintId, errorId, describedBy };
}

export function FieldLabel({ htmlFor, id, optional, children, className }: { htmlFor?: string; id?: string; optional?: boolean; children: React.ReactNode; className?: string }) {
  const { t } = useTranslation();
  const Tag = htmlFor ? "label" : "span";
  return (
    <Tag htmlFor={htmlFor} id={id} className={cn("block text-sm font-medium leading-6 text-slate-800", className)}>
      {children}
      {optional && <span className="ml-1 font-normal text-slate-600">{t("ui.optional")}</span>}
    </Tag>
  );
}

export function FieldHint({ id, children }: { id?: string; children?: React.ReactNode }) {
  if (!children) return null;
  return <p id={id} className="mt-1 text-sm leading-5 text-slate-600">{children}</p>;
}

export function FieldError({ id, children }: { id?: string; children?: React.ReactNode }) {
  if (!children) return null;
  return (
    <p id={id} className="mt-1 flex items-start gap-1.5 text-sm leading-5 text-danger-700">
      <CircleAlert aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </p>
  );
}
