"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";

/** Role-aware tabs. Settings is shown to teachers only; the server stays authoritative. */
export function CourseTabs({ courseId, showSettings }: { courseId: string; showSettings: boolean }) {
  const { lang, t } = useTranslation();
  const pathname = usePathname();
  const base = `/${lang}/courses/${courseId}`;
  const tabs = [
    { href: base, label: t("courses.home.tab"), exact: true },
    { href: `${base}/people`, label: t("courses.people.tab") },
    ...(showSettings ? [{ href: `${base}/settings`, label: t("courses.settings.tab") }] : []),
  ];
  return (
    <nav aria-label={t("courses.home.tabsLabel")} className="mb-6 flex gap-1 border-b border-slate-200">
      {tabs.map((tab) => {
        const active = tab.exact ? pathname === tab.href : pathname.startsWith(tab.href);
        return (
          <Link key={tab.href} href={tab.href} aria-current={active ? "page" : undefined}
            className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-semibold ${active ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
