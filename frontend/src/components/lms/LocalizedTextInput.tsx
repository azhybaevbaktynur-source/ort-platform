"use client";

import React, { useId, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { cn, focusRing } from "@/components/ui";
import type { Lang, LocalizedText } from "@/lib/lms/types";

/**
 * One text per selected course language; edits a LocalizedText value. FB8-5 S3 (STAFF_UX_AUDIT 4): with one language
 * it is a plain field; with several, one tab per language named in words ("Русский (основной)", "Кыргызский (пусто)"),
 * and `fallbackHint` adds the line saying an empty translation shows the main language's text (`pickLocalized`).
 */
export function LocalizedTextInput({
  label,
  languages,
  defaultLanguage,
  value,
  onChange,
  multiline = false,
  maxLength,
  required = false,
  disabled,
  fallbackHint = false,
}: {
  label: string;
  languages: Lang[];
  defaultLanguage: Lang;
  value: LocalizedText;
  onChange: (v: LocalizedText) => void;
  multiline?: boolean;
  maxLength?: number;
  required?: boolean;
  disabled?: boolean;
  /** show "an empty translation shows the main language's text" under the field (several languages only) */
  fallbackHint?: boolean;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [active, setActive] = useState<Lang>(defaultLanguage);
  const current: Lang = languages.includes(active) ? active : languages.includes(defaultLanguage) ? defaultLanguage : languages[0];
  const several = languages.length > 1;
  const set = (text: string) => onChange({ ...value, [current]: text });
  const hintId = `${id}-hint`;
  const common = {
    id: `${id}-${current}`,
    value: value[current] ?? "",
    maxLength,
    disabled,
    required: required && current === defaultLanguage,
    "aria-describedby": several && fallbackHint ? hintId : undefined,
    onChange: (e: React.ChangeEvent<HTMLInputElement & HTMLTextAreaElement>) => set(e.target.value),
    className:
      "w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200 disabled:bg-slate-100",
  };
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
        <label htmlFor={`${id}-${current}`} className="text-sm font-medium text-slate-700">
          {label}
          {required && <span aria-hidden="true"> *</span>}
        </label>
        {several && (
          <div role="tablist" aria-label={label} className="flex flex-wrap gap-1">
            {languages.map((l) => {
              const empty = (value[l] ?? "").trim() === "";
              const note = l === defaultLanguage ? t("courses.create.mainNote") : empty ? t("courses.create.empty") : null;
              return (
                <button key={l} type="button" role="tab" aria-selected={l === current} onClick={() => setActive(l)} disabled={disabled}
                  className={cn("min-h-11 rounded-lg px-2.5 py-1 text-xs font-semibold sm:min-h-0", focusRing,
                    l === current ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200")}>
                  {t(`courses.languages.${l}`)}
                  {note && <span className={cn("font-normal", l === current ? "text-white/85" : "text-slate-500")}>{` (${note})`}</span>}
                </button>
              );
            })}
          </div>
        )}
      </div>
      {multiline ? <textarea rows={4} {...common} /> : <input type="text" {...common} />}
      {several && fallbackHint && <p id={hintId} className="mt-1 text-xs leading-5 text-slate-500">{t("courses.create.fallbackHint")}</p>}
    </div>
  );
}
