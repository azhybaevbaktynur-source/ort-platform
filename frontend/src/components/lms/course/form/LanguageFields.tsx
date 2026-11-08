"use client";

/*
 * FB8-5 S3 (STAFF_UX_AUDIT 4, D-FB8-5-6): the course languages as one main language (a select) and optional
 * translations under "Add translations" (a checkbox per other language). Most courses have one language, so the
 * translations stay folded until asked for (open from the start when the course already has some). Replaces the
 * old LanguagePicker (three checkboxes and a default-language radio group).
 */
import React, { useId, useState } from "react";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { LMS_LANGS, type Lang, type LocalizedText } from "@/lib/lms/types";
import { Checkbox, Select, cn, focusRing } from "@/components/ui";

/** The order the pickers list languages in (most courses are Russian or Kyrgyz). */
const PICK_ORDER: Lang[] = ["ru", "ky", "en"];

/** The course languages in the registry order (main language included). */
function ordered(langs: Lang[]): Lang[] {
  return LMS_LANGS.filter((l) => langs.includes(l));
}

/**
 * The new main language and translations after the main language changes. With no translations the course simply
 * changes language; with translations the previous main language stays as a translation (nothing typed is lost).
 */
export function changeMainLanguage(languages: Lang[], from: Lang, to: Lang): Lang[] {
  if (languages.length <= 1) return [to];
  return ordered([...languages.filter((l) => l !== from), from, to]);
}

/** With one language, the text typed under the old main language moves to the new one. */
export function moveSingleLanguageText(value: LocalizedText, languages: Lang[], from: Lang, to: Lang): LocalizedText {
  if (languages.length > 1 || from === to) return value;
  const text = value[from];
  return text === undefined ? value : { [to]: text };
}

export function LanguageFields({ languages, defaultLanguage, onChange, disabled, idPrefix = "course" }: {
  languages: Lang[];
  defaultLanguage: Lang;
  /** `from` is the main language before the change (equal to `defaultLanguage` when only translations changed) */
  onChange: (languages: Lang[], defaultLanguage: Lang, from: Lang) => void;
  disabled?: boolean;
  idPrefix?: string;
}) {
  const { t } = useTranslation();
  const panelId = useId();
  const translations = languages.filter((l) => l !== defaultLanguage);
  const [open, setOpen] = useState(translations.length > 0);
  const others = PICK_ORDER.filter((l) => l !== defaultLanguage);

  const toggle = (l: Lang, on: boolean) => {
    const next = on ? ordered([...languages, l]) : languages.filter((x) => x !== l);
    onChange(next, defaultLanguage, defaultLanguage);
  };

  return (
    <div className="space-y-2">
      <Select id={`${idPrefix}-main-language`} label={t("courses.create.mainLanguage")} value={defaultLanguage} disabled={disabled}
        hint={t("courses.create.mainLanguageHint")}
        onChange={(e) => {
          const to = e.target.value as Lang;
          onChange(changeMainLanguage(languages, defaultLanguage, to), to, defaultLanguage);
        }}
        options={PICK_ORDER.map((l) => ({ value: l, label: t(`courses.languages.${l}`) }))} />
      <div>
        <button type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((v) => !v)} disabled={disabled}
          className={cn("inline-flex min-h-11 items-center gap-1.5 rounded-lg text-sm font-medium text-brand-700 hover:text-brand-800 sm:min-h-9", focusRing)}>
          <ChevronRight aria-hidden="true" className={cn("h-4 w-4 transition-transform", open && "rotate-90")} />
          {t("courses.create.addTranslations")}
          {translations.length > 0 && (
            <span className="font-normal text-slate-600">
              {` (${translations.map((l) => t(`courses.languages.${l}`)).join(", ")})`}
            </span>
          )}
        </button>
        <div id={panelId} hidden={!open} className="mt-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2">
          <p className="pt-1 text-sm leading-6 text-slate-600">{t("courses.create.translationsHint")}</p>
          <fieldset disabled={disabled} className="flex flex-wrap gap-x-6">
            <legend className="sr-only">{t("courses.create.addTranslations")}</legend>
            {others.map((l) => (
              <Checkbox key={l} id={`${idPrefix}-translation-${l}`} label={t(`courses.languages.${l}`)} checked={languages.includes(l)}
                onChange={(e) => toggle(l, e.target.checked)} />
            ))}
          </fieldset>
        </div>
      </div>
    </div>
  );
}
