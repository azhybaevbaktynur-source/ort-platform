"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { Header } from "@/components/common/Header";
import { ShieldCheck, Database, UploadCloud, BarChart3, GraduationCap, LogOut, BookOpenCheck } from "lucide-react";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { lang, t } = useTranslation();
  const { user, userProfile, loading, signOut } = useAuth();

  useEffect(() => {
    if (!loading) {
      if (!user) {
        router.push(`/${lang}/login?redirect=${encodeURIComponent(pathname)}`);
      } else if (userProfile && userProfile.role !== "admin") {
        // Strictly protect admin portal: kick students to dashboard
        router.push(`/${lang}/dashboard`);
      }
    }
  }, [loading, user, userProfile, router, lang, pathname]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-950 text-slate-300">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-xs text-slate-400 font-medium">{t("common.loading")}</span>
        </div>
      </div>
    );
  }

  if (!user || userProfile?.role !== "admin") {
    return null;
  }

  const navLinks = [
    {
      name: t("nav.admin.examManagement"),
      href: `/${lang}/exams`,
      icon: BookOpenCheck,
    },
    {
      name: t("nav.admin.questionBank"),
      href: `/${lang}/questions`,
      icon: Database,
    },
    {
      name: t("nav.admin.bulkUpload"),
      href: `/${lang}/bulk-upload`,
      icon: UploadCloud,
    },
    {
      name: t("nav.admin.studentAnalytics"),
      href: `/${lang}/analytics`,
      icon: BarChart3,
    },
  ];

  return (
    <div className="flex min-h-screen bg-slate-50">
      {/* Admin Sidebar */}
      <aside className="w-64 bg-slate-950 text-slate-300 min-h-screen flex flex-col border-r border-slate-800">
        <div className="p-6 border-b border-slate-800 flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center text-white font-bold text-base shadow-sm">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <span className="font-bold text-white text-base tracking-tight block">
              {lang === "ky" ? "ОРТ Администратор" : "ОРТ Администратор"}
            </span>
            <span className="text-[11px] text-indigo-400 block font-medium">
              Admin & Management Suite
            </span>
          </div>
        </div>

        <nav className="flex-1 px-4 py-4 space-y-1.5">
          <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500 px-3 py-2">
            {lang === "ky" ? "Башкаруу панели" : "Панель управления"}
          </div>
          {navLinks.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || pathname.startsWith(item.href + "/");

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center px-3.5 py-2.5 text-sm font-medium rounded-xl transition-all ${
                  isActive
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:bg-slate-900 hover:text-white"
                }`}
              >
                <Icon className="w-5 h-5 mr-3 flex-shrink-0" />
                <span className="truncate">{item.name}</span>
              </Link>
            );
          })}

          <div className="pt-6">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500 px-3 py-2">
              {lang === "ky" ? "Окуучу режими" : "Режим ученика"}
            </div>
            <Link
              href={`/${lang}/dashboard`}
              className="flex items-center px-3.5 py-2.5 text-sm font-medium rounded-xl text-slate-400 hover:bg-slate-900 hover:text-white transition-all"
            >
              <GraduationCap className="w-5 h-5 mr-3 text-brand-400" />
              <span>{lang === "ky" ? "Окуучу порталына өтүү" : "Перейти к ученику"}</span>
            </Link>
          </div>
        </nav>

        {/* Admin profile footer */}
        <div className="p-4 border-t border-slate-800 flex items-center justify-between text-xs">
          <div className="flex items-center space-x-2.5 truncate flex-1 min-w-0">
            <div className="w-8 h-8 rounded-full bg-indigo-700/50 border border-indigo-500/50 flex items-center justify-center font-bold text-white text-xs flex-shrink-0">
              {userProfile?.displayName ? userProfile.displayName.slice(0, 2).toUpperCase() : "АД"}
            </div>
            <div className="truncate">
              <div className="font-semibold text-white truncate">
                {userProfile?.displayName || user?.displayName || (lang === "ky" ? "Администратор" : "Администратор")}
              </div>
              <div className="text-slate-400 text-[10px] truncate">
                {userProfile?.email || user?.email || "admin@ort.kg"}
              </div>
            </div>
          </div>

          <button
            onClick={async () => {
              await signOut();
              router.push(`/${lang}/login`);
            }}
            title={t("common.logout")}
            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-900 transition-colors ml-2 flex-shrink-0"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        <Header />
        <main className="flex-1 p-6 md:p-8 overflow-y-auto">
          <div className="max-w-7xl mx-auto">{children}</div>
        </main>
      </div>
    </div>
  );
}
