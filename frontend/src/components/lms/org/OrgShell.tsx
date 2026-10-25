"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { getOrg, type OrgSummaryOut } from "@/lib/lms/organizations";
import { Loading, OrgBadge, OrgError } from "./OrgUi";

interface OrgCtx {
  org: OrgSummaryOut;
  /** Suspended organization: write actions are disabled (server enforces). */
  readOnly: boolean;
  reload: () => Promise<void>;
}

const OrgContext = createContext<OrgCtx | null>(null);

export function useOrg(): OrgCtx {
  const c = useContext(OrgContext);
  if (!c) throw new Error("useOrg must be used within OrgShell");
  return c;
}

/** Org admin area frame: loads GET /org/{orgId}, side nav, suspended banner, no-access state. */
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
      <div role="alert" className="rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <h1 className="text-xl font-bold text-slate-900">{t("organizations.noAccess.title")}</h1>
        <p className="mt-2 text-sm text-slate-600">{t("organizations.noAccess.body")}</p>
        <Link href={`/${lang}/courses`} className="mt-4 inline-block text-sm font-medium text-brand-700 hover:underline">{t("organizations.noAccess.back")}</Link>
      </div>
    );
  }
  if (!org && error) return <OrgError error={error} onRetry={reload} />;
  if (!org) return <Loading />;

  const base = `/${lang}/org/${org.id}`;
  const items = [
    { href: base, label: t("organizations.org.nav.overview"), exact: true },
    { href: `${base}/teachers`, label: t("organizations.org.nav.teachers") },
    { href: `${base}/courses`, label: t("organizations.org.nav.courses") },
  ];
  const readOnly = org.status === "suspended";
  return (
    <OrgContext.Provider value={{ org, readOnly, reload }}>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("organizations.org.area")}</p>
        <h1 className="w-full text-2xl font-bold text-slate-900 sm:w-auto">{org.name}</h1>
        <OrgBadge tone={org.status} labelKey={`organizations.status.${org.status}`} />
      </div>
      {readOnly && (
        <div role="status" className="mb-4 flex items-start gap-2 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
          <p>{t("organizations.org.suspendedBanner")}</p>
        </div>
      )}
      <div className="flex flex-col gap-6 md:flex-row">
        <nav aria-label={t("organizations.org.nav.label")} className="flex flex-wrap gap-1 md:w-56 md:flex-shrink-0 md:flex-col">
          {items.map((i) => {
            const active = i.exact ? pathname === i.href : pathname.startsWith(i.href);
            return (
              <Link key={i.href} href={i.href} aria-current={active ? "page" : undefined}
                className={`inline-flex min-h-[44px] items-center whitespace-nowrap rounded-xl px-3 py-2 text-sm font-medium ${active ? "bg-brand-600 text-white" : "text-slate-700 hover:bg-slate-100"}`}>
                {i.label}
              </Link>
            );
          })}
        </nav>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </OrgContext.Provider>
  );
}
