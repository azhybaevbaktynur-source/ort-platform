"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Building2, ChevronRight } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listMyOrganizations, type MyOrganizationOut } from "@/lib/lms/organizations";
import { EmptyState, LinkButton, LoadingState, PageHeader, cn, focusRing } from "@/components/ui";
import { LoadError, OrgBadge } from "@/components/lms/org/OrgUi";

/** Organization switcher: the organizations the person administers (one = straight in). */
export default function OrgPickerPage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const [orgs, setOrgs] = useState<MyOrganizationOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const rows = (await listMyOrganizations()).filter((o) => o.role === "org_admin");
      setOrgs(rows);
      if (rows.length === 1) router.replace(`/${lang}/org/${rows[0].id}`);
    } catch (e) {
      setError(e);
    }
  }, [lang, router]);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title={t("organizations.org.pickTitle")} />
      {error ? <LoadError error={error} onRetry={load} /> : !orgs ? <LoadingState label={t("lms.common.loading")} /> : orgs.length === 0 ? (
        <EmptyState icon={<Building2 />} title={t("organizations.org.pickEmpty")}
          action={<LinkButton variant="secondary" href={`/${lang}/courses`}>{t("organizations.noAccess.back")}</LinkButton>} />
      ) : (
        <ul className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {orgs.map((o) => (
            <li key={o.id}>
              <Link href={`/${lang}/org/${o.id}`}
                className={cn("flex min-h-14 items-center gap-3 px-4 py-3 hover:bg-slate-50", focusRing, "focus-visible:ring-inset focus-visible:ring-offset-0")}>
                <span className="min-w-0 flex-1 break-words font-semibold text-slate-900">{o.name}</span>
                <OrgBadge tone={o.status} labelKey={`organizations.status.${o.status}`} />
                <ChevronRight aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-500" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
