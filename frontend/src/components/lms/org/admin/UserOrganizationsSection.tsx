"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import {
  addOrganizationMember, listOrganizations, listUserOrganizations, type OrganizationAdminRowOut, type OrgRole,
  type UserOrganizationOut,
} from "@/lib/lms/organizations";
import { fmtApiDate } from "@/lib/format";
import { Button, Card, ConfirmDialog, EmptyState, LoadingState, Select, Table, toast, type TableColumn } from "@/components/ui";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { OrgBadge, OrgError } from "../OrgUi";

const ROLES: OrgRole[] = ["teacher", "org_admin"];

/**
 * Phase 6 S4b, admin user detail (design §3): "Organizations and roles" (GET /platform/users/{id}/organizations)
 * and "Add to organization" (POST /platform/organizations/{id}/members). `readOnly` for system accounts.
 */
export function UserOrganizationsSection({ user, readOnly }: { user: { id: string; display_name: string | null; email: string }; readOnly: boolean }) {
  const { lang, t } = useTranslation();
  const fetchPage = useCallback((cursor: string | null) => listUserOrganizations(user.id, { cursor }), [user.id]);
  const list = useCursorList(fetchPage);
  const state = useTableState(list);
  const [orgs, setOrgs] = useState<OrganizationAdminRowOut[] | null>(null);
  const [orgsError, setOrgsError] = useState<unknown>(null);
  const [orgId, setOrgId] = useState("");
  const [role, setRole] = useState<OrgRole>("teacher");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);

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
      await list.reload();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };

  const columns: TableColumn<UserOrganizationOut>[] = [
    {
      key: "org", header: t("organizations.fields.organization"), primary: true,
      cell: (m) => <Link href={`/${lang}/admin/organizations/${m.organization_id}`} className="break-words font-semibold text-brand-700 hover:underline">{m.organization_name}</Link>,
    },
    {
      key: "role", header: t("organizations.adminUser.role"),
      cell: (m) => (
        <span className="inline-flex flex-wrap items-center justify-end gap-2 sm:justify-start">
          {t(`organizations.roles.${m.role}`)}
          {m.organization_status !== "active" && <OrgBadge tone={m.organization_status} labelKey={`organizations.status.${m.organization_status}`} />}
        </span>
      ),
    },
    { key: "since", header: t("organizations.members.sinceColumn"), nowrap: true, cell: (m) => fmtApiDate(m.created_at, lang) },
  ];
  return (
    <section aria-labelledby="uo-title" className="mb-6">
      <h2 id="uo-title" className="mb-3 text-lg font-semibold leading-7 text-slate-900">{t("organizations.adminUser.orgsTitle")}</h2>
      <Table caption={t("organizations.adminUser.orgsTitle")} columns={columns} rows={list.items} rowKey={(m) => m.organization_id}
        {...state} countText={undefined} empty={<EmptyState title={t("organizations.adminUser.orgsEmpty")} />} />
      <MoreError list={list} />

      {!readOnly && (
        <Card className="mt-3" headingLevel={3} title={t("organizations.adminUser.addToOrg")} description={t("organizations.adminUser.addToOrgHint")}>
          {orgsError ? <OrgError error={orgsError} onRetry={loadOrgs} /> : orgs === null ? <LoadingState label={t("lms.common.loading")} rows={1} /> : (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <Select containerClassName="min-w-0 flex-1" label={t("organizations.fields.organization")} value={orgId} onChange={(e) => setOrgId(e.target.value)}
                placeholder={t("organizations.fields.organizationPick")} options={orgs.map((o) => ({ value: o.id, label: o.name }))} />
              <Select containerClassName="sm:w-56" label={t("organizations.adminUser.role")} value={role} onChange={(e) => setRole(e.target.value as OrgRole)}
                options={ROLES.map((r) => ({ value: r, label: t(`organizations.roles.${r}`) }))} />
              <Button variant="secondary" disabled={!org} onClick={() => { setDialogError(null); setConfirming(true); }}>
                {t("organizations.adminUser.addToOrg")}
              </Button>
            </div>
          )}
        </Card>
      )}
      <ConfirmDialog
        open={confirming && !!org}
        title={t("organizations.adminUser.addTitle")}
        object={org?.name}
        effect={t("organizations.adminUser.addBody", { name, org: org?.name ?? "", role: t(`organizations.roles.${role}`) })}
        confirmLabel={t("organizations.adminUser.addToOrg")}
        busy={busy} error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={() => void add()} onCancel={() => setConfirming(false)}
      />
    </section>
  );
}
