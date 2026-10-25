"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { GraduationCap, UserPlus, Users, UsersRound } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listOrgInvitations, type InvitationOut } from "@/lib/lms/invitations";
import { fmtApiDate } from "@/lib/format";
import { Button, Card, EmptyState, LoadingState, PageHeader, StatTile } from "@/components/ui";
import { useOrg } from "@/components/lms/org/OrgShell";
import { InviteDialog, toastInvitationSent } from "@/components/lms/org/InviteDialog";
import { OrgBadge, OrgError } from "@/components/lms/org/OrgUi";

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
    <div>
      <PageHeader
        title={org.name}
        description={t("organizations.org.area")}
        badge={<OrgBadge tone={org.status} labelKey={`organizations.status.${org.status}`} />}
        primaryAction={
          <Button disabled={readOnly} leftIcon={<UserPlus aria-hidden="true" className="h-4 w-4" />} onClick={() => setInviting(true)}>
            {t("invitations.inviteTeacher")}
          </Button>
        }
      />
      {/* 6a carry-over: tiles link to the list they count. */}
      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile href={`${base}/teachers`} icon={<Users />} label={t("organizations.counts.teachers")} value={c.teachers} />
        <StatTile href={`${base}/courses`} icon={<GraduationCap />} label={t("organizations.counts.courses")} value={c.courses} />
        <StatTile icon={<UsersRound />} label={t("organizations.counts.students")} value={c.students} />
      </div>
      <Card
        title={t("invitations.pendingTitle")}
        padding={pending && pending.length > 0 ? "none" : "md"}
        actions={<Link href={`${base}/teachers`} className="inline-flex min-h-11 items-center text-sm font-semibold text-brand-700 hover:underline sm:min-h-0">{t("invitations.allLink")}</Link>}
      >
        {error ? <OrgError error={error} onRetry={load} /> : pending === null ? <LoadingState label={t("lms.common.loading")} rows={1} /> : pending.length === 0 ? (
          <EmptyState variant="plain" className="py-4" title={t("invitations.pendingEmpty")} />
        ) : (
          <ul className="divide-y divide-slate-100 border-t border-slate-100">
            {pending.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 sm:px-6">
                <span className="min-w-0 break-all font-medium text-slate-900">{i.email}</span>
                <span className="text-sm text-slate-600">{t("invitations.expiresOn", { date: fmtApiDate(i.expires_at, lang) })}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <InviteDialog open={inviting} orgId={org.id} orgName={org.name} onClose={() => setInviting(false)}
        onSent={(inv, email) => { setInviting(false); toastInvitationSent(t, inv, email); void load(); void reload(); }} />
    </div>
  );
}
