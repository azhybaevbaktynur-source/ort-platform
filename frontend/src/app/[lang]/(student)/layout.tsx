"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { Eye, ArrowLeft } from "lucide-react";
import { Sidebar } from "@/components/common/Sidebar";
import { Header } from "@/components/common/Header";
import { useAuth } from "@/lib/auth-context";
import { useTranslation } from "@/lib/i18n/context";

export default function StudentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, userProfile, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const { lang, t } = useTranslation();
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  useEffect(() => {
    setIsMobileNavOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!loading && !user) {
      router.push(`/${lang}/login?redirect=${encodeURIComponent(pathname)}&role=student`);
    }
  }, [loading, user, router, lang, pathname]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-4 border-brand-600 border-t-transparent rounded-full animate-spin" />
          <span className="text-xs text-slate-500 font-medium">{t("common.loading")}</span>
        </div>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar isOpen={isMobileNavOpen} onClose={() => setIsMobileNavOpen(false)} />
      <div className="flex-1 flex flex-col min-w-0">
        {userProfile?.role === "admin" && (
          // Admin viewing the student portal: everything here is a preview (enforced on the server)
          <div className="sticky top-0 z-30 bg-amber-100 border-b border-amber-300 text-amber-900 px-4 py-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs sm:text-sm">
              <Eye className="w-4 h-4 flex-shrink-0" />
              <span className="font-bold">{t("studentMode.banner")}</span>
              <span className="hidden md:inline text-amber-800">{t("studentMode.hint")}</span>
            </div>
            <Link
              href={`/${lang}/exams`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-900 text-white text-xs font-semibold hover:bg-amber-800 transition"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              {t("studentMode.back")}
            </Link>
          </div>
        )}
        <Header onMenuClick={() => setIsMobileNavOpen((prev) => !prev)} />
        <main className="flex-1 p-4 sm:p-6 md:p-8 overflow-y-auto">
          <div className="max-w-7xl mx-auto">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}

