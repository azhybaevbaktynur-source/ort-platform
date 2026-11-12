"use client";

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ShieldAlert } from "lucide-react";
import { useStaffDictionary, useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { useCachedMe } from "@/lib/lms/meCache"; // PERFORMANCE_AUDIT S3
import { getPlatformSummary } from "@/lib/lms/admin";
import type { LmsApiError } from "@/lib/lms/client";
import type { StorageLevel } from "@/lib/lms/storage";
import { AreaShell } from "@/components/ui/AreaShell";
import { EmptyState, LinkButton, LoadingState, type Breadcrumb } from "@/components/ui";

interface AdminSummary {
  pending: number | null;
  storageLevel: StorageLevel | null;
  /** The summary could not be loaded, even after the retries (a value loaded before stays shown). */
  error: LmsApiError | null;
  refresh: () => void;
}
const SummaryContext = createContext<AdminSummary>({ pending: null, storageLevel: null, error: null, refresh: () => {} });
/** FIX_ROUND_2026-11-12 1a: waits before each retry, long enough to span most of a server wake-up. */
const RETRY_MS = [1500, 4000, 8000];
/** A failure worth trying again: no answer, the server starting or busy, or a server error. */
const retryable = (e: LmsApiError) =>
  e?.code === "network" || e?.code === "server_starting" || e?.code === "server_busy" || (e?.status ?? 0) >= 500;
export const useAdminSummary = () => useContext(SummaryContext);

/** Breadcrumbs of an admin page: Admin → section (→ page). */
export function useAdminCrumbs() {
  const { lang, t } = useTranslation();
  return (...rest: Breadcrumb[]): Breadcrumb[] => [{ label: t("shell.areas.platform"), href: `/${lang}/admin` }, ...rest];
}

/** Platform admin area: section nav (`AreaShell`) + client-side guard (the server is authoritative). */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const { lang, t } = useTranslation();
  const staffReady = useStaffDictionary(); // performance audit S4
  const { me: fresh, loading } = useLmsMe();
  const cachedMe = useCachedMe(); // PERFORMANCE_AUDIT S3: the cached answer draws the area at once (no spinner)
  const me = fresh ?? cachedMe;
  const pathname = usePathname();
  const router = useRouter();
  const [pending, setPending] = useState<number | null>(null);
  const [storageLevel, setStorageLevel] = useState<StorageLevel | null>(null);
  const [error, setError] = useState<LmsApiError | null>(null);
  const run = useRef(0); // a newer refresh replaces the retries of an older one
  const isAdmin = !!me?.is_platform_admin;

  // UX rework 2, FIX_ROUND_2026-11-12 1a: retries with growing waits for a slow or waking server; after that only the
  // overview's "Needs attention" card says so (never the whole page), and a failure never clears a value already loaded.
  const refresh = useCallback(() => {
    const id = ++run.current;
    setError(null);
    const load = async (attempt: number): Promise<void> => {
      try {
        const s = await getPlatformSummary();
        if (id !== run.current) return;
        setPending(s.pending_teacher_requests);
        setStorageLevel(s.storage_level);
      } catch (e) {
        if (id !== run.current) return;
        const err = e as LmsApiError;
        if (err?.code === "mfa_enrollment_required") { // S1: set up two-step login first
          setError(err);
          return;
        }
        if (attempt < RETRY_MS.length && retryable(err)) {
          await new Promise((done) => setTimeout(done, RETRY_MS[attempt]));
          if (id === run.current) await load(attempt + 1);
          return;
        }
        setError(err);
      }
    };
    void load(0);
  }, []);
  useEffect(() => { if (isAdmin) refresh(); }, [isAdmin, refresh]);
  const securityPath = `/${lang}/admin/security`;
  const mustEnroll = error?.code === "mfa_enrollment_required";
  useEffect(() => {
    if (mustEnroll && pathname !== securityPath) router.replace(securityPath);
  }, [mustEnroll, pathname, securityPath, router]);

  // Integration fix: only `me` is awaited here; while the staff dictionary loads, AreaShell renders the area hidden under
  // its loading state, so the page's requests go out with `/platform/summary` instead of after the dictionary chunk.
  if (loading && !me) return <LoadingState label={t("lms.common.loading")} />;
  if (!isAdmin) {
    if (!staffReady) return <LoadingState label={t("lms.common.loading")} />;
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
  const g = (k: string) => t(`platformAdmin.nav.groups.${k}`);
  const nav: { href: string; label: string; exact?: boolean; count?: number | null; group?: string; alsoUnder?: string }[] = [
    { href: base, label: t("platformAdmin.nav.overview"), exact: true },
    { href: `${base}/users`, label: t("platformAdmin.nav.users"), group: g("people") },
    { href: `${base}/teacher-requests`, label: t("platformAdmin.nav.teacherRequests"), count: pending, group: g("people") },
    { href: `${base}/organizations`, label: t("organizations.nav.organizations"), group: g("content") },
    { href: `${base}/courses`, label: t("platformAdmin.nav.courses"), group: g("content") },
    { href: `${base}/catalog`, label: t("platformAdmin.nav.catalog"), group: g("content") }, // step 3b S2
    { href: `${base}/exam-templates`, label: t("examTemplates.nav.title"), group: g("content") },
    { href: `${base}/access/settings`, label: t("platformAdmin.nav.plans"), group: g("pro") },
    { href: `${base}/access`, label: t("platformAdmin.nav.proUsers"), exact: true, group: g("pro") },
    { href: `${base}/access/vouchers`, label: t("platformAdmin.nav.gifts"), group: g("pro"), alsoUnder: `${base}/access/batches` },
    { href: `${base}/access/exams`, label: t("platformAdmin.nav.paidExams"), group: g("pro") }, // D-FB8-5-5
    { href: `${base}/services`, label: t("infra.nav"), group: g("system") }, // INFRA_PANEL_DESIGN
    { href: `${base}/storage`, label: t("storage.nav"), group: g("system") },
    { href: `${base}/health`, label: t("platformAdmin.nav.health"), group: g("system") }, // S4 page
    { href: `${base}/audit-log`, label: t("platformAdmin.nav.auditLog"), group: g("system") },
    { href: `${base}/security`, label: t("adminSecurity.nav"), group: g("system") }, // S1 admin security
    { href: `${base}/privacy`, label: t("privacy.admin.title"), group: g("system") }, // Phase 11 S3: data requests
  ];
  const visible = mustEnroll ? nav.filter((i) => i.href === securityPath) : nav;
  const items = visible.map((i) => ({
    href: i.href, label: i.label, count: i.count, group: i.group,
    active: i.exact ? pathname === i.href : pathname === i.href || pathname.startsWith(`${i.href}/`)
      || (!!i.alsoUnder && pathname.startsWith(`${i.alsoUnder}/`)),
  }));
  return (
    <SummaryContext.Provider value={{ pending, storageLevel, error, refresh }}>
      <AreaShell
        label={t("platformAdmin.nav.label")}
        items={items}
        heading={<p className="text-xs font-semibold uppercase tracking-wide text-slate-600">{t("shell.areas.platform")}</p>}
      >
        {mustEnroll && pathname !== securityPath ? <LoadingState label={t("lms.common.loading")} /> : children}
      </AreaShell>
    </SummaryContext.Provider>
  );
}
