import React from "react";
import { LanguageProvider, Language } from "@/lib/i18n/context";
import { AuthProvider } from "@/lib/auth-context";
import { ToastProvider } from "@/components/ui/Toast";
import type { Metadata } from "next";
import enDict from "@/lib/i18n/en.json";
import kyDict from "@/lib/i18n/ky.json";
import ruDict from "@/lib/i18n/ru.json";

// Phase 6b S5b: browser tab title and description per language from i18n (`common.appName`, `landing.badge`).
const META_DICTS = { en: enDict, ky: kyDict, ru: ruDict } as const;

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang } = await params;
  const d = META_DICTS[lang === "ru" || lang === "en" ? lang : "ky"];
  return { title: d.common.appName, description: d.landing.badge };
}

// Pre-render every page for both languages at build time, so pages such as /ky/login are served
// as static files from Vercel's CDN instead of running a server function on each visit.
export function generateStaticParams() {
  return [{ lang: "en" }, { lang: "ky" }, { lang: "ru" }];
}

export default async function LangLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ lang: string }>;
}) {
  const resolvedParams = await params;
  const currentLang = (resolvedParams.lang === "ru" || resolvedParams.lang === "en" ? resolvedParams.lang : "ky") as Language;

  return (
    <LanguageProvider initialLang={currentLang}>
      <AuthProvider>
        <ToastProvider>
          {children}
        </ToastProvider>
      </AuthProvider>
    </LanguageProvider>
  );
}
