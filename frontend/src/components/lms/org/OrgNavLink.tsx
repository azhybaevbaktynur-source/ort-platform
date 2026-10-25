"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Building2, ChevronDown } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listMyOrganizations, type MyOrganizationOut } from "@/lib/lms/organizations";

/**
 * Header link to the org admin area: one link when the person administers one organization,
 * a small menu (switcher) when several, nothing otherwise. Fails silently (navigation only).
 */
export function OrgNavLink({ enabled, className }: { enabled: boolean; className: (href: string) => string }) {
  const { lang, t } = useTranslation();
  const pathname = usePathname();
  const [orgs, setOrgs] = useState<MyOrganizationOut[]>([]);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    listMyOrganizations()
      .then((rows) => { if (alive) setOrgs((Array.isArray(rows) ? rows : []).filter((o) => o.role === "org_admin")); })
      .catch(() => { if (alive) setOrgs([]); });
    return () => { alive = false; };
  }, [enabled]);

  if (orgs.length === 0) return null;
  const base = `/${lang}/org`;
  if (orgs.length === 1) {
    const href = `${base}/${orgs[0].id}`;
    return (
      <Link href={href} className={className(href)}>
        <Building2 className="h-4 w-4" aria-hidden="true" />{t("organizations.nav.organization")}
      </Link>
    );
  }
  return (
    <details className="relative">
      <summary className={`${className(base)} cursor-pointer list-none`}>
        <Building2 className="h-4 w-4" aria-hidden="true" />{t("organizations.nav.organizations")}
        <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
      </summary>
      <ul className="absolute left-0 z-30 mt-1 min-w-[14rem] rounded-xl border border-slate-200 bg-white p-1 shadow-lg">
        {orgs.map((o) => (
          <li key={o.id}>
            <Link href={`${base}/${o.id}`} aria-current={pathname.startsWith(`${base}/${o.id}`) ? "page" : undefined}
              className="flex min-h-[44px] items-center rounded-lg px-3 text-sm text-slate-700 hover:bg-slate-100">
              {o.name}
            </Link>
          </li>
        ))}
      </ul>
    </details>
  );
}
