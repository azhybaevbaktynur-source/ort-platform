import React from "react";
import { LanguageProvider, Language } from "@/lib/i18n/context";
import { AuthProvider } from "@/lib/auth-context";

// Pre-render every page for both languages at build time, so pages such as /ky/login are served
// as static files from Vercel's CDN instead of running a server function on each visit.
export function generateStaticParams() {
  return [{ lang: "ky" }, { lang: "ru" }];
}

export default async function LangLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ lang: string }>;
}) {
  const resolvedParams = await params;
  const currentLang = (resolvedParams.lang === "ru" ? "ru" : "ky") as Language;

  return (
    <LanguageProvider initialLang={currentLang}>
      <AuthProvider>
        {children}
      </AuthProvider>
    </LanguageProvider>
  );
}
