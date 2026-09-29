import React from "react";
import { LanguageProvider, Language } from "@/lib/i18n/context";
import { AuthProvider } from "@/lib/auth-context";

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
