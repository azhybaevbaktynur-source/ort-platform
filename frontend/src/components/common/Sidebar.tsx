"use client";

import React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import {
  LayoutDashboard,
  BookOpen,
  Clock,
  BookX,
  BarChart3,
  Flame,
  LogOut,
  X,
  GraduationCap,
} from "lucide-react";

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen = false, onClose }) => {
  const pathname = usePathname();
  const router = useRouter();
  const { lang, t } = useTranslation();
  const { userProfile, user, signOut } = useAuth();

  const navItems = [
    {
      name: t("nav.dashboard"),
      href: `/${lang}/dashboard`,
      icon: LayoutDashboard,
    },
    {
      name: t("nav.practice"),
      href: `/${lang}/practice`,
      icon: BookOpen,
    },
    {
      name: t("nav.mockTests"),
      href: `/${lang}/mock-tests`,
      icon: Clock,
    },
    {
      name: t("nav.mistakes"),
      href: `/${lang}/mistakes`,
      icon: BookX,
    },
    {
      name: t("nav.analytics"),
      href: `/${lang}/progress`,
      icon: BarChart3,
    },
    {
      name: t("nav.courses"),
      href: `/${lang}/courses`,
      icon: GraduationCap,
    },
  ];

  const renderContent = () => (
    <div className="flex flex-col h-full">
      {/* Brand Logo & Mobile Close */}
      <div className="p-6 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-brand-600 flex items-center justify-center text-white font-bold text-base shadow-sm shadow-brand-500/30">
            ОРТ
          </div>
          <div>
            <span className="font-bold text-white text-base tracking-tight block">
              {t("common.appName")}
            </span>
            <span className="text-[11px] text-slate-400 block font-medium">
              ОРТ / ЖРТ Даярдоо
            </span>
          </div>
        </div>

        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="md:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition cursor-pointer"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Return to Admin Panel Button (for Admin accounts viewing student mode) */}
      {userProfile?.role === "admin" && (
        <div className="px-4 pt-4">
          <Link
            href={`/${lang}/analytics`}
            onClick={onClose}
            className="w-full flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white font-bold text-xs shadow-md shadow-indigo-950/50 border border-indigo-400/30 transition-all hover:scale-[1.02] active:scale-[0.98] group"
          >
            <span className="text-sm group-hover:-translate-x-0.5 transition-transform">🔙</span>
            <span>{lang === "ky" ? "Админ-панелге кайтуу" : "Вернуться в админ-панель"}</span>
          </Link>
        </div>
      )}

      {/* Quick Streak Indicator */}
      <div className="p-4 mx-4 my-4 rounded-xl bg-slate-800/80 border border-slate-700/50">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center text-amber-400 font-semibold gap-1.5">
            <Flame className="w-4 h-4 fill-amber-400 text-amber-400" />
            <span>7 {lang === "ky" ? "күн катары менен" : "дней подряд"}</span>
          </div>
          <span className="text-slate-400 font-medium text-[10px]">🔥 Active</span>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-4 space-y-1.5 overflow-y-auto">
        <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-3 py-2">
          {lang === "ky" ? "Окуучу менюсу" : "Обучение"}
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/");

          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onClose}
              className={`flex items-center px-3.5 py-2.5 text-sm font-medium rounded-xl transition-all ${
                isActive
                  ? "bg-brand-600 text-white shadow-sm shadow-brand-500/20"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white"
              }`}
            >
              <Icon className="w-5 h-5 mr-3 flex-shrink-0" />
              <span className="truncate">{item.name}</span>
            </Link>
          );
        })}
      </nav>

      {/* User profile footer */}
      <div className="p-4 border-t border-slate-800 flex items-center justify-between text-xs">
        <div className="flex items-center space-x-2.5 truncate flex-1 min-w-0">
          <div className="w-8 h-8 rounded-full bg-brand-600/40 border border-brand-500/40 flex items-center justify-center font-bold text-white text-xs flex-shrink-0">
            {userProfile?.displayName ? userProfile.displayName.slice(0, 2).toUpperCase() : "ОК"}
          </div>
          <div className="truncate">
            <div className="font-semibold text-white truncate">
              {userProfile?.displayName || user?.displayName || (lang === "ky" ? "Окуучу" : "Ученик")}
            </div>
            <div className="text-slate-400 text-[10px] truncate">
              {userProfile?.email || user?.email || "student@ort.kg"}
            </div>
          </div>
        </div>

        <button
          onClick={async () => {
            if (onClose) onClose();
            await signOut();
            router.push(`/${lang}/login`);
          }}
          title={t("common.logout")}
          className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition-colors ml-2 flex-shrink-0 cursor-pointer"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Persistent Sidebar */}
      <aside className="hidden md:flex w-64 bg-slate-900 text-slate-300 min-h-screen flex-col border-r border-slate-800 shrink-0">
        {renderContent()}
      </aside>

      {/* Mobile Backdrop Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 backdrop-blur-xs z-40 md:hidden animate-in fade-in"
          onClick={onClose}
        />
      )}

      {/* Mobile Slide-in Drawer */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 text-slate-300 flex flex-col border-r border-slate-800 shadow-2xl transform transition-transform duration-300 ease-in-out md:hidden ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {renderContent()}
      </aside>
    </>
  );
};
