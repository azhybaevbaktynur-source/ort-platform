"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { LMS_LANGS, type Lang } from "@/lib/lms/types";

/** Pick the course languages (subset of en/ru/ky, at least one) and the default among them. */
export function LanguagePicker({
  languages,
  defaultLanguage,
  onChange,
  disabled,
}: {
  languages: Lang[];
  defaultLanguage: Lang;
  onChange: (languages: Lang[], defaultLanguage: Lang) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const toggle = (l: Lang) => {
    const has = languages.includes(l);
    if (has && languages.length === 1) return; // at least one language
    const next = has ? languages.filter((x) => x !== l) : LMS_LANGS.filter((x) => languages.includes(x) || x === l);
    const def = next.includes(defaultLanguage) ? defaultLanguage : next[0];
    onChange(next, def);
  };
  return (
    <div className="space-y-4">
      <fieldset disabled={disabled}>
        <legend className="mb-1 text-sm font-medium text-slate-700">{t("courses.create.languages")}</legend>
        <div className="flex flex-wrap gap-3">
          {LMS_LANGS.map((l) => (
            <label key={l} className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-3 py-2 text-sm">
              <input type="checkbox" checked={languages.includes(l)} onChange={() => toggle(l)}
                disabled={languages.length === 1 && languages.includes(l)} />
              {t(`courses.languages.${l}`)}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset disabled={disabled}>
        <legend className="mb-1 text-sm font-medium text-slate-700">{t("courses.create.defaultLanguage")}</legend>
        <div className="flex flex-wrap gap-3">
          {languages.map((l) => (
            <label key={l} className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-3 py-2 text-sm">
              <input type="radio" name="default-language" checked={defaultLanguage === l} onChange={() => onChange(languages, l)} />
              {t(`courses.languages.${l}`)}
            </label>
          ))}
        </div>
      </fieldset>
    </div>
  );
}
