"use client";

import React, { useId, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { Lang, LocalizedText } from "@/lib/lms/types";

/** One tab per selected course language; edits a LocalizedText value. */
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
}) {
  const { t } = useTranslation();
  const id = useId();
  const [active, setActive] = useState<Lang>(defaultLanguage);
  const current: Lang = languages.includes(active) ? active : languages[0];
  const set = (text: string) => onChange({ ...value, [current]: text });
  const common = {
    id: `${id}-${current}`,
    value: value[current] ?? "",
    maxLength,
    disabled,
    required: required && current === defaultLanguage,
    onChange: (e: React.ChangeEvent<HTMLInputElement & HTMLTextAreaElement>) => set(e.target.value),
    className:
      "w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200 disabled:bg-slate-100",
  };
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <label htmlFor={`${id}-${current}`} className="text-sm font-medium text-slate-700">
          {label}
          {required && <span aria-hidden="true"> *</span>}
        </label>
        <div role="tablist" aria-label={label} className="flex gap-1">
          {languages.map((l) => (
            <button key={l} type="button" role="tab" aria-selected={l === current} onClick={() => setActive(l)}
              className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${l === current ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
              {l.toUpperCase()}
              {l === defaultLanguage && <span className="sr-only"> ({t("courses.create.defaultLanguage")})</span>}
              {(value[l] ?? "").trim() === "" && <span className="sr-only"> ({t("courses.create.empty")})</span>}
            </button>
          ))}
        </div>
      </div>
      {multiline ? <textarea rows={4} {...common} /> : <input type="text" {...common} />}
    </div>
  );
}
