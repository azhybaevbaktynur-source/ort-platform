"use client";

// Phase 8b S4: small shared pieces of the constructor tabs (radio cards, field issues, "Go to" targets).
import React, { useId } from "react";
import type { SpecIssue } from "@/lib/lms/examTemplateTypes";
import { LMS_LANGS, type Lang, type LocalizedText } from "@/lib/lms/types";
import { FieldError, cn } from "@/components/ui";
import { locStartsWith } from "./ui";
import type { SpecDraft } from "./specDraft";

export type Update = (fn: (d: SpecDraft) => SpecDraft) => void;
export type FieldErr = (...prefix: (string | number)[]) => string | undefined;
export type ConstructorTab = "structure" | "scoring" | "display" | "sample" | "versions";

/**
 * Phase 8b S5: the language tab a localized field opens on: the UI language when it has text, else the first
 * language that has text (a template written in Russian opens on RU for an English UI instead of an empty box).
 */
export function filledLang(v: LocalizedText | null | undefined, lang: Lang): Lang {
  if (v?.[lang]?.trim()) return lang;
  return LMS_LANGS.find((l) => v?.[l]?.trim()) ?? lang;
}

/** DOM id of a spec field, the target of the issues bar's "Go to" links. */
export const fieldId = (...loc: (string | number)[]) => `tplf-${loc.map(String).join("-")}`;

/** Which tab shows the field at `loc`. */
export function tabOfLoc(loc: (string | number)[]): ConstructorTab {
  const top = String(loc[0] ?? "");
  if (top === "scoring" || top === "result_view") return "scoring";
  if (top === "display_mode" || top === "passage_display" || top === "lock_scope") return "display";
  return "structure";
}

/** Translated issues whose `loc` starts with `prefix` (one line under the field). */
export function useFieldIssues(issues: SpecIssue[], what: (i: SpecIssue) => string): FieldErr {
  return (...prefix) => {
    const hit = issues.filter((i) => locStartsWith(i.loc, prefix) && (prefix.length > 1 || i.loc.length <= 1));
    return hit.length ? Array.from(new Set(hit.map(what))).join(" ") : undefined;
  };
}

export interface RadioCardOption {
  value: string;
  label: string;
  description?: string;
  illustration?: React.ReactNode;
}

/** A radio group drawn as cards (44 px targets; the whole card is the label). */
export function RadioCards({ id, legend, hint, value, options, onChange, disabled, error, columns = 1 }: {
  id?: string;
  legend: string;
  hint?: string;
  value: string;
  options: RadioCardOption[];
  onChange: (v: string) => void;
  disabled?: boolean;
  error?: string;
  columns?: 1 | 2;
}) {
  const name = useId();
  return (
    <fieldset id={id} className="min-w-0" aria-invalid={error ? true : undefined}>
      <legend className="text-sm font-medium leading-6 text-slate-800">{legend}</legend>
      {hint && <p className="text-sm text-slate-600">{hint}</p>}
      <div className={cn("mt-2 grid grid-cols-1 gap-2", columns === 2 && "sm:grid-cols-2")}>
        {options.map((o) => {
          const on = o.value === value;
          return (
            <label key={o.value || "_"} className={cn(
              "flex min-h-11 items-start gap-3 rounded-xl border px-3 py-2.5",
              disabled ? "cursor-not-allowed opacity-70" : "cursor-pointer",
              on ? "border-brand-500 bg-brand-50" : "border-slate-200 hover:bg-slate-50",
              "focus-within:ring-2 focus-within:ring-brand-600",
            )}>
              <input type="radio" name={name} className="mt-1 h-4 w-4 shrink-0 accent-brand-600" checked={on} disabled={disabled}
                onChange={() => onChange(o.value)} />
              <span className="min-w-0 flex-1">
                <span className="block font-medium text-slate-900">{o.label}</span>
                {o.description && <span className="block text-sm leading-5 text-slate-600">{o.description}</span>}
              </span>
              {o.illustration && <span aria-hidden="true" className="hidden shrink-0 sm:block">{o.illustration}</span>}
            </label>
          );
        })}
      </div>
      <FieldError>{error}</FieldError>
    </fieldset>
  );
}
