"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { UserPlus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listOrgInvitations, type InvitationOut } from "@/lib/lms/invitations";
import { fmtApiDate } from "@/lib/format";
import { useOrg } from "@/components/lms/org/OrgShell";
import { InviteDialog, toastInvitationSent } from "@/components/lms/org/InviteDialog";
import { EmptyBox, Loading, OrgError, StatTile, btn } from "@/components/lms/org/OrgUi";

export default function OrgOverviewPage() {
  const { lang, t } = useTranslation();
  const { org, readOnly, reload } = useOrg();
  const [pending, setPending] = useState<InvitationOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [inviting, setInviting] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const page = await listOrgInvitations(org.id, { state: "pending", limit: 5 });
      setPending(page.items.filter((i) => i.state === "pending"));
    } catch (e) {
      setError(e);
    }
  }, [org.id]);
  useEffect(() => { void load(); }, [load]);

  const c = org.usage;
  const base = `/${lang}/org/${org.id}`;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold text-slate-900">{t("organizations.org.overviewTitle")}</h2>
        <button type="button" className={btn.primary} disabled={readOnly} onClick={() => setInviting(true)}>
          <UserPlus className="h-4 w-4" aria-hidden="true" />{t("invitations.inviteTeacher")}
        </button>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile label={t("organizations.counts.teachers")} value={c.teachers} />
        <StatTile label={t("organizations.counts.courses")} value={c.courses} />
        <StatTile label={t("organizations.counts.students")} value={c.students} />
      </div>
      <section aria-labelledby="ov-pending">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 id="ov-pending" className="text-lg font-semibold text-slate-900">{t("invitations.pendingTitle")}</h3>
          <Link href={`${base}/teachers`} className="text-sm font-medium text-brand-700 hover:underline">{t("invitations.allLink")}</Link>
        </div>
        {error ? <OrgError error={error} onRetry={load} /> : pending === null ? <Loading /> : pending.length === 0 ? (
          <EmptyBox text={t("invitations.pendingEmpty")} />
        ) : (
          <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white text-sm">
            {pending.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                <span className="min-w-0 break-all font-medium text-slate-900">{i.email}</span>
                <span className="text-xs text-slate-500">{t("invitations.expiresOn", { date: fmtApiDate(i.expires_at, lang) })}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <InviteDialog open={inviting} orgId={org.id} orgName={org.name} onClose={() => setInviting(false)}
        onSent={(inv, email) => { setInviting(false); toastInvitationSent(t, inv, email); void load(); void reload(); }} />
    </div>
  );
}
