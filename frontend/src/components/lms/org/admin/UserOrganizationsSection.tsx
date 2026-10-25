"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import {
  addOrganizationMember, listOrganizations, listUserOrganizations, type OrganizationAdminRowOut, type OrgRole,
  type UserOrganizationOut,
} from "@/lib/lms/organizations";
import { fmtApiDate } from "@/lib/format";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { Pager } from "@/components/lms/Pager";
import { EmptyBox, Loading, OrgBadge, OrgError, btn, cardCls, inputCls, labelCls } from "../OrgUi";
import { toast } from "@/components/ui/Toast";

const ROLES: OrgRole[] = ["teacher", "org_admin"];

/**
 * Phase 6 S4b, admin user detail (design §3): "Organizations and roles" (GET /platform/users/{id}/organizations)
 * and "Add to organization" (POST /platform/organizations/{id}/members). `readOnly` for system accounts.
 */
export function UserOrganizationsSection({ user, readOnly }: { user: { id: string; display_name: string | null; email: string }; readOnly: boolean }) {
  const { lang, t } = useTranslation();
  const [items, setItems] = useState<UserOrganizationOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [orgs, setOrgs] = useState<OrganizationAdminRowOut[] | null>(null);
  const [orgsError, setOrgsError] = useState<unknown>(null);
  const [orgId, setOrgId] = useState("");
  const [role, setRole] = useState<OrgRole>("teacher");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listUserOrganizations(user.id, { cursor: next });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [user.id]);
  useEffect(() => { void load(); }, [load]);

  const loadOrgs = useCallback(async () => {
    setOrgsError(null);
    try {
      setOrgs((await listOrganizations({ status: "active", limit: 100 })).items);
    } catch (e) {
      setOrgsError(e);
    }
  }, []);
  useEffect(() => { if (!readOnly) void loadOrgs(); }, [readOnly, loadOrgs]);

  const name = user.display_name || user.email;
  const org = orgs?.find((o) => o.id === orgId) ?? null;
  const add = async () => {
    if (!org) return;
    setBusy(true);
    setDialogError(null);
    try {
      await addOrganizationMember(org.id, user.id, role);
      toast.success(t("organizations.adminUser.added", { name, org: org.name }));
      setConfirming(false);
      setOrgId("");
      await load();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="uo-title" className="mb-6">
      <h2 id="uo-title" className="mb-2 text-lg font-semibold text-slate-900">{t("organizations.adminUser.orgsTitle")}</h2>
      {error ? <OrgError error={error} onRetry={() => load()} className="mb-3" /> : null}
      {loading && items.length === 0 && !error && <Loading />}
      {!loading && !error && items.length === 0 && <EmptyBox text={t("organizations.adminUser.orgsEmpty")} />}
      {items.length > 0 && (
        <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white text-sm">
          {items.map((m) => (
            <li key={m.organization_id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3">
              <div className="min-w-0 flex-1 basis-56">
                <Link href={`/${lang}/admin/organizations/${m.organization_id}`} className="font-medium text-brand-700 hover:underline">{m.organization_name}</Link>
                <p className="truncate text-xs text-slate-500">{t("organizations.members.since", { date: fmtApiDate(m.created_at, lang) })}</p>
              </div>
              <span className="text-xs text-slate-700">{t(`organizations.roles.${m.role}`)}</span>
              {m.organization_status !== "active" && <OrgBadge tone={m.organization_status} labelKey={`organizations.status.${m.organization_status}`} />}
            </li>
          ))}
        </ul>
      )}
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />

      {!readOnly && (
        <div className={`${cardCls} mt-3`}>
          <h3 className="mb-1 font-semibold text-slate-900">{t("organizations.adminUser.addToOrg")}</h3>
          <p className="mb-3 text-sm text-slate-600">{t("organizations.adminUser.addToOrgHint")}</p>
          {orgsError ? <OrgError error={orgsError} onRetry={loadOrgs} /> : orgs === null ? <Loading /> : (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="min-w-0 flex-1">
                <label htmlFor="uo-org" className={labelCls}>{t("organizations.fields.organization")}</label>
                <select id="uo-org" value={orgId} onChange={(e) => setOrgId(e.target.value)} className={inputCls}>
                  <option value="">{t("organizations.fields.organizationPick")}</option>
                  {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </select>
              </div>
              <div className="sm:w-56">
                <label htmlFor="uo-role" className={labelCls}>{t("organizations.adminUser.role")}</label>
                <select id="uo-role" value={role} onChange={(e) => setRole(e.target.value as OrgRole)} className={inputCls}>
                  {ROLES.map((r) => <option key={r} value={r}>{t(`organizations.roles.${r}`)}</option>)}
                </select>
              </div>
              <button type="button" className={btn.secondary} disabled={!org} onClick={() => { setDialogError(null); setConfirming(true); }}>
                {t("organizations.adminUser.addToOrg")}
              </button>
            </div>
          )}
        </div>
      )}
      <ConfirmDialog
        open={confirming && !!org}
        title={t("organizations.adminUser.addTitle", { name, org: org?.name ?? "" })}
        body={t("organizations.adminUser.addBody", { name, org: org?.name ?? "", role: t(`organizations.roles.${role}`) })}
        confirmLabel={t("organizations.adminUser.addToOrg")}
        busy={busy} error={dialogError} onConfirm={() => void add()} onCancel={() => setConfirming(false)}
      />
    </section>
  );
}
