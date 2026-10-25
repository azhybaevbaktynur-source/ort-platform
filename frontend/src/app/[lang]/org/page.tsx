"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { listMyOrganizations, type MyOrganizationOut } from "@/lib/lms/organizations";
import { EmptyBox, Loading, OrgBadge, OrgError } from "@/components/lms/org/OrgUi";

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

  if (error) return <OrgError error={error} onRetry={load} />;
  if (!orgs) return <Loading />;
  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-4 text-2xl font-bold text-slate-900">{t("organizations.org.pickTitle")}</h1>
      {orgs.length === 0 ? (
        <EmptyBox text={t("organizations.org.pickEmpty")}>
          <Link href={`/${lang}/courses`} className="text-sm font-medium text-brand-700 hover:underline">{t("organizations.noAccess.back")}</Link>
        </EmptyBox>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
          {orgs.map((o) => (
            <li key={o.id}>
              <Link href={`/${lang}/org/${o.id}`} className="flex min-h-[56px] items-center justify-between gap-3 px-4 py-3 hover:bg-slate-50">
                <span className="font-medium text-slate-900">{o.name}</span>
                <OrgBadge tone={o.status} labelKey={`organizations.status.${o.status}`} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
