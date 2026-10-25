"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import kyDict from "./ky.json";
import ruDict from "./ru.json";
import enDict from "./en.json";

export type Language = "en" | "ky" | "ru";

interface LanguageContextType {
  lang: Language;
  setLang: (lang: Language) => void;
  t: (keyPath: string, params?: Record<string, string | number>) => string;
}

const dictionaries: Record<Language, any> = {
  ky: kyDict,
  ru: ruDict,
  en: enDict,
};

/** Value at a dotted path, or undefined. */
function lookupPath(dict: any, keys: string[]): unknown {
  let current = dict;
  for (const key of keys) {
    if (current && typeof current === "object" && key in current) current = current[key];
    else return undefined;
  }
  return current;
}

/** String at `keyPath` in `lang`; a path missing in `lang` falls back to Russian. */
function resolveKey(lang: Language, keyPath: string): string | undefined {
  const keys = keyPath.split(".");
  let value = lookupPath(dictionaries[lang], keys);
  if (value === undefined) value = lookupPath(dictionaries["ru"], keys);
  return typeof value === "string" ? value : undefined;
}

const pluralRulesCache: Partial<Record<Language, Intl.PluralRules>> = {};
function pluralCategory(lang: Language, count: number): string {
  let rules = pluralRulesCache[lang];
  if (!rules) {
    try { rules = new Intl.PluralRules(lang); } catch { rules = new Intl.PluralRules("en"); }
    pluralRulesCache[lang] = rules;
  }
  return rules.select(count);
}

/** The number that picks the plural form: `count`, else `n` (numbers or numeric strings). */
function pluralCount(params?: Record<string, string | number>): number | null {
  if (!params) return null;
  for (const name of ["count", "n"]) {
    const v = params[name];
    if (v === undefined || v === "") continue;
    const num = typeof v === "number" ? v : Number(v);
    if (Number.isFinite(num)) return num;
  }
  return null;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({
  children,
  initialLang = "ky",
}: {
  children: React.ReactNode;
  initialLang?: Language;
}) {
  const [lang, setLangState] = useState<Language>(initialLang);

  useEffect(() => {
    const saved = localStorage.getItem("ort_preferred_language") as Language;
    if (saved && (saved === "ky" || saved === "ru" || saved === "en")) {
      setLangState(saved);
    }
  }, []);

  // Phase 6b: the document language follows the UI language (screen readers, hyphenation, api.ts messages).
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = (newLang: Language) => {
    setLangState(newLang);
    localStorage.setItem("ort_preferred_language", newLang);
  };

  const t = (keyPath: string, params?: Record<string, string | number>): string => {
    // Phase 6b S11b: plural forms. With a numeric `count` (or `n`) param, `key_one` / `key_few` / `key_many` /
    // `key_other` (Intl.PluralRules of the UI language) win over the plain key when they exist.
    const count = pluralCount(params);
    let template: string | undefined;
    if (count !== null) template = resolveKey(lang, `${keyPath}_${pluralCategory(lang, count)}`);
    if (template === undefined) template = resolveKey(lang, keyPath);
    if (template === undefined) return keyPath;

    let result = template;
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        result = result.replace(new RegExp(`{${k}}`, "g"), String(v));
      });
    }
    return result;
  };

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useTranslation() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useTranslation must be used within a LanguageProvider");
  }
  return context;
}

