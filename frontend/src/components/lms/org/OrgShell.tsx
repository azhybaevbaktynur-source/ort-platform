"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useParams, usePathname } from "next/navigation";
import { Building2, TriangleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { getOrg, type OrgSummaryOut } from "@/lib/lms/organizations";
import { AreaShell } from "@/components/ui/AreaShell";
import { EmptyState, LinkButton, LoadingState, type Breadcrumb } from "@/components/ui";
import { LoadError, OrgBadge } from "./OrgUi";

interface OrgCtx {
  org: OrgSummaryOut;
  /** Suspended organization: write actions are disabled (server enforces). */
  readOnly: boolean;
  reload: () => Promise<void>;
  /** Breadcrumbs of an org page: organization → section (→ page). */
  crumbs: (...rest: Breadcrumb[]) => Breadcrumb[];
}

const OrgContext = createContext<OrgCtx | null>(null);

export function useOrg(): OrgCtx {
  const c = useContext(OrgContext);
  if (!c) throw new Error("useOrg must be used within OrgShell");
  return c;
}

/** Org admin area frame: loads GET /org/{orgId}, section nav (`AreaShell`), suspended banner, no-access state. */
export function OrgShell({ children }: { children: React.ReactNode }) {
  const { lang, t } = useTranslation();
  const { orgId } = useParams<{ orgId: string }>();
  const pathname = usePathname();
  const [org, setOrg] = useState<OrgSummaryOut | null>(null);
  const [error, setError] = useState<unknown>(null);

  const reload = useCallback(async () => {
    try {
      setOrg(await getOrg(orgId));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [orgId]);
  useEffect(() => { setOrg(null); void reload(); }, [reload]);

  const status = (error as { status?: number } | null)?.status;
  if (!org && (status === 403 || status === 404)) {
    return (
      <EmptyState
        icon={<Building2 />}
        title={t("organizations.noAccess.title")}
        description={t("organizations.noAccess.body")}
        action={<LinkButton href={`/${lang}/courses`} variant="secondary">{t("organizations.noAccess.back")}</LinkButton>}
      />
    );
  }
  if (!org && error) return <LoadError error={error} onRetry={reload} />;
  if (!org) return <LoadingState label={t("lms.common.loading")} />;

  const base = `/${lang}/org/${org.id}`;
  const items = [
    { href: base, label: t("organizations.org.nav.overview"), active: pathname === base },
    { href: `${base}/teachers`, label: t("organizations.org.nav.teachers"), active: pathname.startsWith(`${base}/teachers`) },
    { href: `${base}/courses`, label: t("organizations.org.nav.courses"), active: pathname.startsWith(`${base}/courses`) },
    // --- Phase 9 S2 begin --- (PHASE_9_DESIGN 8.1: Overview · Teachers · Courses · Departments · Shared banks · Roster import · Exam templates · Settings)
    { href: `${base}/departments`, label: t("departments.nav"), active: pathname.startsWith(`${base}/departments`) },
    { href: `${base}/shared-banks`, label: t("sharedBanks.nav"), active: pathname.startsWith(`${base}/shared-banks`) },
    { href: `${base}/roster-import`, label: t("organizations.org.rosterImport"), active: pathname.startsWith(`${base}/roster-import`) },
    // --- Phase 9 S2 end ---
    // --- Phase 7b S4 ---
    { href: `${base}/exam-templates`, label: t("examTemplates.nav.title"), active: pathname.startsWith(`${base}/exam-templates`) },
    // --- Phase 9 S2 ---
    { href: `${base}/settings`, label: t("orgSettings.nav"), active: pathname.startsWith(`${base}/settings`) },
  ];
  const readOnly = org.status === "suspended";
  const crumbs = (...rest: Breadcrumb[]): Breadcrumb[] => [{ label: org.name, href: base }, ...rest];
  return (
    <OrgContext.Provider value={{ org, readOnly, reload, crumbs }}>
      <AreaShell
        label={t("organizations.org.nav.label")}
        items={items}
        heading={
          <>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">{t("organizations.org.area")}</p>
            <p className="mt-1 break-words text-base font-semibold leading-6 text-slate-900">{org.name}</p>
            {readOnly && <div className="mt-1"><OrgBadge tone={org.status} labelKey={`organizations.status.${org.status}`} /></div>}
          </>
        }
        banner={readOnly ? (
          <div role="status" className="mb-4 flex items-start gap-3 rounded-2xl border border-warning-200 bg-warning-50 p-4 text-sm leading-6 text-warning-900">
            <TriangleAlert className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
            <p>{t("organizations.org.suspendedBanner")}</p>
          </div>
        ) : undefined}
      >
        {children}
      </AreaShell>
    </OrgContext.Provider>
  );
}
