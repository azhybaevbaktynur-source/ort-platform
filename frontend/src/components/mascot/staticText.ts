"use client";

import { usePathname } from "next/navigation";
import en from "@/lib/i18n/en.json";
import ky from "@/lib/i18n/ky.json";
import ru from "@/lib/i18n/ru.json";

const DICTS = { en: en.mascot, ky: ky.mascot, ru: ru.mascot } as const;
export type StaticLang = keyof typeof DICTS;

/** Error and 404 screens outside the language providers: the language comes from the first URL segment (default ky). */
export function useStaticText() {
  const first = (usePathname() ?? "").split("/")[1];
  const lang: StaticLang = first === "ru" || first === "en" ? first : "ky";
  return { lang, m: DICTS[lang] };
}
