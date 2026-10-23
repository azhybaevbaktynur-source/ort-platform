"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { getPlatformSummary } from "@/lib/lms/admin";

const SummaryContext = createContext<{ pending: number | null; refresh: () => void }>({ pending: null, refresh: () => {} });
export const useAdminSummary = () => useContext(SummaryContext);

/** Admin side nav + client-side guard (server is authoritative). */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const { lang, t } = useTranslation();
  const { me, loading } = useLmsMe();
  const pathname = usePathname();
  const [pending, setPending] = useState<number | null>(null);
  const isAdmin = !!me?.is_platform_admin;

  const refresh = useCallback(() => {
    getPlatformSummary().then((s) => setPending(s.pending_teacher_requests)).catch(() => setPending(null));
  }, []);
  useEffect(() => { if (isAdmin) refresh(); }, [isAdmin, refresh]);

  if (loading && !me) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;
  if (!isAdmin) {
    return (
      <div role="alert" className="rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <h1 className="text-xl font-bold text-slate-900">{t("platformAdmin.notAuthorized.title")}</h1>
        <p className="mt-2 text-sm text-slate-600">{t("platformAdmin.notAuthorized.body")}</p>
        <Link href={`/${lang}/courses`} className="mt-4 inline-block text-sm font-medium text-brand-700 hover:underline">{t("platformAdmin.notAuthorized.back")}</Link>
      </div>
    );
  }

  const items = [
    { href: `/${lang}/admin`, label: t("platformAdmin.nav.overview"), exact: true },
    { href: `/${lang}/admin/teacher-requests`, label: t("platformAdmin.nav.teacherRequests"), badge: pending },
    { href: `/${lang}/admin/users`, label: t("platformAdmin.nav.users") },
    { href: `/${lang}/admin/courses`, label: t("platformAdmin.nav.courses") },
    { href: `/${lang}/admin/audit-log`, label: t("platformAdmin.nav.auditLog") },
    { href: `/${lang}/admin/storage`, label: t("storage.nav") },
  ];
  return (
    <SummaryContext.Provider value={{ pending, refresh }}>
      <div className="flex flex-col gap-6 md:flex-row">
        <nav aria-label={t("platformAdmin.nav.label")} className="flex gap-1 overflow-x-auto md:w-56 md:flex-shrink-0 md:flex-col">
          {items.map((i) => {
            const active = i.exact ? pathname === i.href : pathname.startsWith(i.href);
            return (
              <Link key={i.href} href={i.href} aria-current={active ? "page" : undefined}
                className={`flex items-center justify-between whitespace-nowrap rounded-xl px-3 py-2 text-sm font-medium ${active ? "bg-brand-600 text-white" : "text-slate-700 hover:bg-slate-100"}`}>
                {i.label}
                {i.badge ? <span className="ml-2 rounded-full bg-amber-400 px-2 text-xs font-bold text-slate-900">{i.badge}</span> : null}
              </Link>
            );
          })}
        </nav>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </SummaryContext.Provider>
  );
}
