"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { TargetScoreModal } from "@/components/ui/TargetScoreModal";
import {
  LayoutDashboard,
  BookOpen,
  Clock,
  BookX,
  BarChart3,
  Flame,
  Target,
  LogOut,
} from "lucide-react";

export const Sidebar: React.FC = () => {
  const pathname = usePathname();
  const router = useRouter();
  const { lang, t } = useTranslation();
  const { userProfile, user, signOut, updateTargetScore } = useAuth();
  const [isTargetModalOpen, setIsTargetModalOpen] = useState(false);

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
  ];

  return (
    <aside className="w-64 bg-slate-900 text-slate-300 min-h-screen flex flex-col border-r border-slate-800">
      {/* Brand Logo */}
      <div className="p-6 border-b border-slate-800 flex items-center space-x-3">
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

      {/* Quick Streak & Target Score Badge */}
      <div className="p-4 mx-4 my-4 rounded-xl bg-slate-800/80 border border-slate-700/50 space-y-2">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center text-amber-400 font-semibold gap-1">
            <Flame className="w-4 h-4 fill-amber-400 text-amber-400" />
            <span>7 {lang === "ky" ? "күн стрик" : "дней ударно"}</span>
          </div>
          <span className="text-slate-400 font-medium text-[10px]">🔥 Active</span>
        </div>

        <button
          type="button"
          onClick={() => setIsTargetModalOpen(true)}
          className="w-full flex items-center justify-between text-xs pt-1.5 border-t border-slate-700/60 hover:bg-slate-800/80 p-1.5 rounded-lg transition text-left cursor-pointer group"
          title={lang === "ky" ? "Максаттуу баллды өзгөртүү" : "Нажмите, чтобы изменить целевой балл"}
        >
          <div className="flex items-center text-emerald-400 font-semibold gap-1.5">
            <Target className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
            <span>
              {lang === "ky" ? "Максат" : "Цель"}: {userProfile?.target_score || 215}
            </span>
          </div>
          <span className="text-[10px] text-emerald-300 bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/60 font-medium group-hover:border-emerald-500 transition">
            {(userProfile?.target_score || 215) >= 219
              ? (lang === "ky" ? "Алтын" : "Золото")
              : (userProfile?.target_score || 215) >= 175
              ? (lang === "ky" ? "Грант" : "Грант")
              : (lang === "ky" ? "ОРТ" : "ОРТ")}
          </span>
        </button>
      </div>

      <TargetScoreModal
        isOpen={isTargetModalOpen}
        initialScore={userProfile?.target_score || 215}
        onClose={() => setIsTargetModalOpen(false)}
        onSave={async (newScore) => {
          await updateTargetScore(newScore);
        }}
      />

      {/* Navigation Links */}
      <nav className="flex-1 px-4 space-y-1.5">
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
            await signOut();
            router.push(`/${lang}/login`);
          }}
          title={t("common.logout")}
          className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition-colors ml-2 flex-shrink-0"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </aside>
  );
};

