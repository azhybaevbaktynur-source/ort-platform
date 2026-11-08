"use client";

import React, { createContext, useContext, useState, useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import staffPrefixes from "./staffPrefixes.json";

export type Language = "en" | "ky" | "ru";
type Dictionary = Record<string, any>;

interface LanguageContextType {
  lang: Language;
  setLang: (lang: Language) => void;
  t: (keyPath: string, params?: Record<string, string | number>) => string;
  /** The staff part of the current language's dictionary is loaded (performance audit S4). */
  staffReady: boolean;
}

/*
 * S5 performance (low-end phones): the three dictionaries are about 1 MB together (230 kB compressed, more than half
 * of every page's JavaScript). Each is now its own chunk: a page loads only its language, another language is
 * loaded the first time it is chosen. `?lazy` (lazy-json.d.ts) keeps these imports apart from the small static
 * reads of the same files (mascot/staticText.ts), which webpack trims to the parts they use.
 */
const dictionaries: Partial<Record<Language, Dictionary>> = {};
const loading: Partial<Record<Language, Promise<void>>> = {};
const LOADERS: Record<Language, () => Promise<{ default: unknown }>> = {
  en: () => import("./generated/en.core.json?lazy"),
  ky: () => import("./generated/ky.core.json?lazy"),
  ru: () => import("./generated/ru.core.json?lazy"),
};

/*
 * Performance audit S4: each language is split at build time (scripts/split_dictionaries.mjs, by key prefix) into `core`
 * (every page) and `staff` (editors, admin, organization, grading set-up: a separate chunk). Staff areas preload it with
 * useStaffDictionary(); a staff key asked anywhere else loads it on demand and renders empty (never the raw key) until it
 * has arrived. Never requested on the server, so server HTML and the first client render agree.
 */
const staffDictionaries: Partial<Record<Language, Dictionary>> = {};
const staffLoading: Partial<Record<Language, Promise<void>>> = {};
const staffListeners = new Set<() => void>();
const STAFF_LOADERS: Record<Language, () => Promise<{ default: unknown }>> = {
  en: () => import("./generated/en.staff.json?lazy"),
  ky: () => import("./generated/ky.staff.json?lazy"),
  ru: () => import("./generated/ru.staff.json?lazy"),
};

/** Called by dictionaries/<lang>.tsx when it renders. */
export function registerDictionary(lang: Language, dictionary: unknown) {
  dictionaries[lang] ??= dictionary as Dictionary;
}

function loadStaff(lang: Language): Promise<void> {
  staffLoading[lang] ??= retrying(STAFF_LOADERS[lang]).then((m) => {
    staffDictionaries[lang] = m.default as Dictionary;
    staffListeners.forEach((fn) => fn());
  });
  return staffLoading[lang];
}

/** A download that never rejects: when it fails (no network) it is tried again later; meanwhile the server's HTML stays. */
function retrying<T>(load: () => Promise<T>): Promise<T> {
  return new Promise<T>((resolve) => {
    const attempt = (n: number) => {
      load().then(resolve, () => { setTimeout(() => attempt(n + 1), Math.min(30_000, 1000 * 2 ** n)); });
    };
    attempt(0);
  });
}

function loadDictionary(lang: Language): Promise<void> {
  loading[lang] ??= retrying(LOADERS[lang]).then((m) => registerDictionary(lang, m.default));
  return loading[lang];
}

/** Language switch: when the staff part was in use, the new language's staff part arrives with its core. */
function loadDictionaryFor(next: Language, withStaff: boolean): Promise<void> {
  return Promise.all([loadDictionary(next), withStaff ? loadStaff(next) : undefined]).then(() => undefined);
}

/*
 * The page's own language arrives with the page: rendered through next/dynamic, its chunk is named in the server's
 * HTML, so the browser fetches it together with the other scripts, and hydration waits for it (the server's HTML stays
 * on screen) instead of fetching it only after the app's code ran.
 */
const PAGE_DICTIONARY: Record<Language, React.ComponentType<{ children: React.ReactNode }>> = {
  en: dynamic(() => retrying(() => import("./dictionaries/en"))),
  ky: dynamic(() => retrying(() => import("./dictionaries/ky"))),
  ru: dynamic(() => retrying(() => import("./dictionaries/ru"))),
};

/** The key belongs to the staff part (same rule as scripts/split_dictionaries.mjs). */
const isStaffKey = (keyPath: string) => staffPrefixes.some((x) => keyPath === x || keyPath.startsWith(x + "."));

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
  if (value === undefined) value = lookupPath(staffDictionaries[lang], keys);
  if (value === undefined) value = lookupPath(dictionaries["ru"], keys);
  if (value === undefined) value = lookupPath(staffDictionaries["ru"], keys);
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
  const PageDictionary = PAGE_DICTIONARY[initialLang];
  const [lang, setLangState] = useState<Language>(initialLang);
  const wanted = useRef<Language>(initialLang);
  const [, setStaffTick] = useState(0);

  useEffect(() => {
    const listener = () => setStaffTick((n) => n + 1);
    staffListeners.add(listener);
    return () => { staffListeners.delete(listener); };
  }, []);

  /** Shows `next` once its dictionary is here; a later choice wins over a slower earlier one. */
  const switchTo = (next: Language) => {
    wanted.current = next;
    if (dictionaries[next] && (!staffDictionaries[lang] || staffDictionaries[next])) { setLangState(next); return; }
    loadDictionaryFor(next, !!staffDictionaries[lang]).then(() => { if (wanted.current === next) setLangState(next); }).catch(() => undefined);
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
    if (template === undefined) {
      // a staff key whose part has not arrived yet renders empty (and loads it), never the raw key; any other missing
      // key stays the key itself (callers test `t(k) !== k`)
      if (!staffDictionaries[lang] && isStaffKey(keyPath) && typeof window !== "undefined") { void loadStaff(lang); return ""; }
      return keyPath;
    }

    let result = template;
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        result = result.replace(new RegExp(`{${k}}`, "g"), String(v));
      });
    }
    return result;
  };

  return (
    <LanguageContext.Provider value={{ lang, setLang, t, staffReady: !!staffDictionaries[lang] }}>
      <PageDictionary>{children}</PageDictionary>
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


/**
 * Staff areas (AreaShell, AdminShell, OrgShell, the course staff layout) call this to preload the staff part of the
 * dictionary. Returns whether it is here; until then the caller shows its neutral loading state.
 */
export function useStaffDictionary(enabled = true): boolean {
  const { lang, staffReady } = useTranslation();
  useEffect(() => {
    if (enabled && !staffDictionaries[lang]) void loadStaff(lang);
  }, [enabled, lang]);
  return !enabled || staffReady;
}
