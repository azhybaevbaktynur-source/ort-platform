"use client";

import React, { createContext, use, useContext, useState, useEffect, useRef } from "react";

export type Language = "en" | "ky" | "ru";
type Dictionary = Record<string, any>;

interface LanguageContextType {
  lang: Language;
  setLang: (lang: Language) => void;
  t: (keyPath: string, params?: Record<string, string | number>) => string;
}

/*
 * S5 performance (low-end phones): the three dictionaries are about 1 MB together (230 kB compressed, more than half
 * of every page's JavaScript). Each is now its own chunk: a page loads only its language, another language is
 * loaded the first time it is chosen.
 */
const dictionaries: Partial<Record<Language, Dictionary>> = {};
const loading: Partial<Record<Language, Promise<void>>> = {};
const LOADERS: Record<Language, () => Promise<{ default: unknown }>> = {
  en: () => import("./en.json?lazy"),
  ky: () => import("./ky.json?lazy"),
  ru: () => import("./ru.json?lazy"),
};

/** Never rejects: a failed download (no network) is tried again later, and until then the server's HTML stays. */
function loadDictionary(lang: Language): Promise<void> {
  loading[lang] ??= new Promise<void>((resolve) => {
    const attempt = (n: number) => {
      LOADERS[lang]().then((m) => { dictionaries[lang] = m.default as Dictionary; resolve(); })
        .catch(() => { setTimeout(() => attempt(n + 1), Math.min(30_000, 1000 * 2 ** n)); });
    };
    attempt(0);
  });
  return loading[lang];
}

/** Value at a dotted path, or undefined. */
function lookupPath(dict: any, keys: string[]): unknown {
  let current = dict;
  for (const key of keys) {
    if (current && typeof current === "object" && key in current) current = current[key];
    else return undefined;
  }
  return current;
}

/** String at `keyPath` in `lang`; a path missing in `lang` falls back to Russian (when loaded). */
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
  // The page's language before anything renders: the server waits for it, and in the browser hydration waits while
  // the server's HTML stays on screen. Loaded once; later pages of the session find it here.
  if (!dictionaries[initialLang]) use(loadDictionary(initialLang));
  const [lang, setLangState] = useState<Language>(initialLang);
  const wanted = useRef<Language>(initialLang);

  /** Shows `next` once its dictionary is here; a later choice wins over a slower earlier one. */
  const switchTo = (next: Language) => {
    wanted.current = next;
    if (dictionaries[next]) { setLangState(next); return; }
    loadDictionary(next).then(() => { if (wanted.current === next) setLangState(next); }).catch(() => undefined);
  };

  useEffect(() => {
    const saved = localStorage.getItem("ort_preferred_language") as Language;
    if (saved && (saved === "ky" || saved === "ru" || saved === "en")) {
      switchTo(saved);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Phase 6b: the document language follows the UI language (screen readers, hyphenation, api.ts messages).
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = (newLang: Language) => {
    switchTo(newLang);
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

