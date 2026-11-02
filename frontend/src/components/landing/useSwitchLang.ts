"use client";

import { usePathname, useRouter } from "next/navigation";
import { useTranslation, type Language } from "@/lib/i18n/context";

export const LANDING_LANGS: Language[] = ["en", "ky", "ru"];

/** Change the language and stay on the same page (same as `switchLang` in components/lms/LmsShell.tsx). */
export function useSwitchLang(): (l: Language) => void {
  const { setLang } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();
  return (l) => {
    setLang(l);
    const rest = pathname.replace(/^\/(en|ky|ru)(?=\/|$)/, "");
    const qs = typeof window !== "undefined" ? window.location.search : "";
    router.push(`/${l}${rest}${qs}`);
  };
}
