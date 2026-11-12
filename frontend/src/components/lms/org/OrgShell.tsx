"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { Building2, ShieldCheck, TriangleAlert } from "lucide-react";
import { useStaffDictionary, useTranslation } from "@/lib/i18n/context";
import { getOrg, type OrgSummaryOut } from "@/lib/lms/organizations";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { setCurrentOrg } from "@/lib/lms/currentOrg"; // item 4: the header's organization switcher reads it
import { AreaShell } from "@/components/ui/AreaShell";
import { EmptyState, LinkButton, LoadingState, focusRing, type Breadcrumb } from "@/components/ui";
import { LoadError, OrgBadge } from "./OrgUi";

interface OrgCtx {
  org: OrgSummaryOut;
  /** Suspended organization: write actions are disabled (server enforces). Not for the platform admin (D-ORG-2). */
  readOnly: boolean;
  /** Item 4: the platform admin is here from outside the tree (no membership); every write is audited so. */
  actingAsPlatformAdmin: boolean;
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
  const staffReady = useStaffDictionary(); // performance audit S4
  const { orgId } = useParams<{ orgId: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const { me } = useLmsMe();
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
  // Accounts: a personal organization has no area of its own; only the platform admin opens it here.
  const personal = org?.kind === "personal" && !me?.is_platform_admin;
  useEffect(() => {
    if (personal && me) router.replace(`/${lang}/courses`); // step 3a S3: no ?view=
  }, [personal, me, lang, router]);

  // --- Admin orgs (item 4) begin --- (ADMIN_ORGS_DESIGN §2.4, §2.5)
  // The header shows a foreign organization as the active choice of its switcher: set here, cleared when leaving.
  useEffect(() => {
    setCurrentOrg(org ? { id: org.id, name: org.name, acting_as: org.acting_as } : null);
  }, [org]);
  useEffect(() => () => setCurrentOrg(null), []);
  const acting = org?.acting_as === "platform_admin"; // derived by the server from memberships, displayed only
  const orgName = org?.name ?? "";
  // The browser tab says so too: "{organization} · platform admin" (restored when the area is left).
  useEffect(() => {
    if (!acting || !orgName) return;
    const title = `${orgName} · ${t("organizations.org.titleSuffix")}`;
    const previous = document.title === title ? t("common.appName") : document.title;
    document.title = title;
    const timer = window.setTimeout(() => { document.title = title; }, 0); // after the route's own metadata
    return () => {
      window.clearTimeout(timer);
      if (document.title === title) document.title = previous;
    };
  }, [acting, orgName, pathname, t]);
  // --- Admin orgs (item 4) end ---

  if (!staffReady) return <LoadingState label={t("lms.common.loading")} />;
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
  if (!org || personal) return <LoadingState label={t("lms.common.loading")} />;

  const base = `/${lang}/org/${org.id}`;
  const items = [
    { href: base, label: t("organizations.org.nav.overview"), active: pathname === base },
    { href: `${base}/teachers`, label: t("organizations.org.nav.teachers"), active: pathname.startsWith(`${base}/teachers`) },
    { href: `${base}/courses`, label: t("organizations.org.nav.courses"), active: pathname.startsWith(`${base}/courses`) },
    // --- Phase 9 S2 begin --- (PHASE_9_DESIGN 8.1: Overview · Teachers · Courses · Departments · Shared banks · Roster import · Exam templates · Settings)
    { href: `${base}/departments`, label: t("departments.nav"), active: pathname.startsWith(`${base}/departments`) },
    // item 4: shared-bank content stays closed to the platform admin (decision A4), so the link is hidden for them
    ...(acting ? [] : [{ href: `${base}/shared-banks`, label: t("sharedBanks.nav"), active: pathname.startsWith(`${base}/shared-banks`) }]),
    { href: `${base}/roster-import`, label: t("organizations.org.rosterImport"), active: pathname.startsWith(`${base}/roster-import`) },
    // --- Phase 9 S2 end ---
    { href: `${base}/analytics`, label: t("analytics.nav"), active: pathname.startsWith(`${base}/analytics`) },
    // --- Phase 7b S4 ---
    { href: `${base}/exam-templates`, label: t("examTemplates.nav.title"), active: pathname.startsWith(`${base}/exam-templates`) },
    // --- Phase 9 S2 ---
    { href: `${base}/settings`, label: t("orgSettings.nav"), active: pathname.startsWith(`${base}/settings`) },
  ];
  const suspended = org.status === "suspended";
  const readOnly = suspended && !acting; // D-ORG-2: the platform admin keeps writing (the server allows it)
  const crumbs = (...rest: Breadcrumb[]): Breadcrumb[] => [{ label: org.name, href: base }, ...rest];
  return (
    <OrgContext.Provider value={{ org, readOnly, actingAsPlatformAdmin: acting, reload, crumbs }}>
      <AreaShell
        label={t("organizations.org.nav.label")}
        items={items}
        heading={
          <>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
              {t(acting ? "organizations.org.areaPlatformAdmin" : "organizations.org.area")}
            </p>
            <p className="mt-1 break-words text-base font-semibold leading-6 text-slate-900">{org.name}</p>
            {suspended && <div className="mt-1"><OrgBadge tone={org.status} labelKey={`organizations.status.${org.status}`} /></div>}
          </>
        }
        banner={acting || suspended ? (
          <>
            {acting && (
              // item 4 (§2.4): brand-tinted, not amber (amber stays for "suspended")
              <div role="note" data-testid="acting-as-platform-admin"
                className="mb-4 flex flex-col gap-1 rounded-2xl border border-brand-200 bg-brand-50 px-4 py-3 text-sm leading-6 text-brand-900 sm:flex-row sm:items-center sm:gap-4">
                <p className="flex min-w-0 flex-1 items-start gap-3">
                  <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-brand-700" aria-hidden="true" />
                  <span className="min-w-0 break-words">{t("organizations.org.actingAsPlatformAdmin", { org: org.name })}</span>
                </p>
                <Link href={`/${lang}/admin/organizations/${org.id}`}
                  className={`inline-flex min-h-11 shrink-0 items-center self-start rounded pl-8 font-semibold text-brand-700 hover:underline sm:min-h-0 sm:self-auto sm:pl-0 ${focusRing}`}>
                  {t("organizations.org.actingAsPlatformAdminBack")}
                </Link>
              </div>
            )}
            {suspended && (
              <div role="status" className="mb-4 flex items-start gap-3 rounded-2xl border border-warning-200 bg-warning-50 p-4 text-sm leading-6 text-warning-900">
                <TriangleAlert className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
                <p>{t("organizations.org.suspendedBanner")}</p>
              </div>
            )}
          </>
        ) : undefined}
      >
        {children}
      </AreaShell>
    </OrgContext.Provider>
  );
}
