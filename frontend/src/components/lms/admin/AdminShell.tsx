"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { ShieldAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { getPlatformSummary } from "@/lib/lms/admin";
import { AreaShell } from "@/components/ui/AreaShell";
import { EmptyState, LinkButton, LoadingState, type Breadcrumb } from "@/components/ui";

const SummaryContext = createContext<{ pending: number | null; refresh: () => void }>({ pending: null, refresh: () => {} });
export const useAdminSummary = () => useContext(SummaryContext);

/** Breadcrumbs of an admin page: Admin → section (→ page). */
export function useAdminCrumbs() {
  const { lang, t } = useTranslation();
  return (...rest: Breadcrumb[]): Breadcrumb[] => [{ label: t("shell.areas.platform"), href: `/${lang}/admin` }, ...rest];
}

/** Platform admin area: section nav (`AreaShell`) + client-side guard (the server is authoritative). */
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

  if (loading && !me) return <LoadingState label={t("lms.common.loading")} />;
  if (!isAdmin) {
    return (
      <EmptyState
        icon={<ShieldAlert />}
        title={t("platformAdmin.notAuthorized.title")}
        description={t("platformAdmin.notAuthorized.body")}
        action={<LinkButton href={`/${lang}/courses`} variant="secondary">{t("platformAdmin.notAuthorized.back")}</LinkButton>}
      />
    );
  }

  const base = `/${lang}/admin`;
  const nav = [
    { href: base, label: t("platformAdmin.nav.overview"), exact: true },
    { href: `${base}/organizations`, label: t("organizations.nav.organizations") },
    { href: `${base}/teacher-requests`, label: t("platformAdmin.nav.teacherRequests"), count: pending },
    { href: `${base}/users`, label: t("platformAdmin.nav.users") },
    { href: `${base}/courses`, label: t("platformAdmin.nav.courses") },
    { href: `${base}/exam-templates`, label: t("examTemplates.nav.title") }, // Phase 7b S4
    { href: `${base}/audit-log`, label: t("platformAdmin.nav.auditLog") },
    { href: `${base}/storage`, label: t("storage.nav") },
  ];
  const items = nav.map((i) => ({
    href: i.href, label: i.label, count: i.count,
    active: i.exact ? pathname === i.href : pathname === i.href || pathname.startsWith(`${i.href}/`),
  }));
  return (
    <SummaryContext.Provider value={{ pending, refresh }}>
      <AreaShell
        label={t("platformAdmin.nav.label")}
        items={items}
        heading={<p className="text-xs font-semibold uppercase tracking-wide text-slate-600">{t("shell.areas.platform")}</p>}
      >
        {children}
      </AreaShell>
    </SummaryContext.Provider>
  );
}
