"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  SLUG_RE, createOrganization, listOrganizations, slugify, type OrganizationAdminRowOut, type OrganizationOut, type OrgStatus,
} from "@/lib/lms/organizations";
import { fmtApiDate } from "@/lib/format";
import { Button, Dialog, EmptyState, FilterBar, Input, PageHeader, Select, Table, type TableColumn } from "@/components/ui";
import { OrgBadge, OrgError } from "@/components/lms/org/OrgUi";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useCursorList, useDebounced } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";

const STATUSES: (OrgStatus | "")[] = ["", "active", "suspended"];

export default function AdminOrganizationsPage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const crumbs = useAdminCrumbs();
  const [input, setInput] = useState("");
  const q = useDebounced(input);
  const [status, setStatus] = useState<OrgStatus | "">("");
  const [creating, setCreating] = useState(false);
  const fetchPage = useCallback((cursor: string | null) => listOrganizations({ q, status, cursor }), [q, status]);
  const list = useCursorList(fetchPage);
  const state = useTableState(list);

  const n = (v: number | undefined) => (typeof v === "number" ? v : "—");
  const columns: TableColumn<OrganizationAdminRowOut>[] = [
    {
      key: "name", header: t("organizations.fields.name"), primary: true,
      cell: (o) => (
        <>
          <Link href={`/${lang}/admin/organizations/${o.id}`} className="font-semibold text-brand-700 hover:underline">{o.name}</Link>
          <span className="block text-sm font-normal text-slate-600">{o.slug}</span>
        </>
      ),
    },
    { key: "status", header: t("organizations.admin.status"), cell: (o) => <OrgBadge tone={o.status} labelKey={`organizations.status.${o.status}`} /> },
    { key: "admins", header: t("organizations.counts.orgAdmins"), align: "right", cell: (o) => n(o.org_admins) },
    { key: "teachers", header: t("organizations.counts.teachers"), align: "right", cell: (o) => n(o.teachers) },
    { key: "courses", header: t("organizations.counts.courses"), align: "right", cell: (o) => n(o.courses) },
    { key: "created", header: t("organizations.admin.created"), nowrap: true, cell: (o) => fmtApiDate(o.created_at, lang) },
  ];
  const filtered = !!(q || status);
  return (
    <div>
      <PageHeader
        title={t("organizations.admin.title")}
        breadcrumbs={crumbs({ label: t("organizations.admin.title") })}
        primaryAction={<Button leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />} onClick={() => setCreating(true)}>{t("organizations.admin.create")}</Button>}
      />
      <Table
        caption={t("organizations.admin.title")}
        columns={columns}
        rows={list.items}
        rowKey={(o) => o.id}
        {...state}
        search={
          <FilterBar
            search={{ value: input, onChange: setInput, label: t("lms.common.search"), placeholder: t("organizations.admin.searchPlaceholder") }}
            canReset={filtered} onReset={() => { setInput(""); setStatus(""); }}
          >
            <Select label={t("organizations.admin.status")} value={status} onChange={(e) => setStatus(e.target.value as OrgStatus | "")}
              options={STATUSES.map((s) => ({ value: s, label: s ? t(`organizations.status.${s}`) : t("organizations.admin.anyStatus") }))} />
          </FilterBar>
        }
        empty={
          <EmptyState
            title={filtered ? t("organizations.admin.emptySearch") : t("organizations.admin.empty")}
            action={!filtered ? <Button variant="secondary" onClick={() => setCreating(true)}>{t("organizations.admin.create")}</Button> : undefined}
          />
        }
      />
      <MoreError list={list} />
      <CreateOrganizationDialog open={creating} onClose={() => setCreating(false)}
        onCreated={(o) => { setCreating(false); router.push(`/${lang}/admin/organizations/${o.id}`); }} />
    </div>
  );
}

function CreateOrganizationDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (o: OrganizationOut) => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => { if (open) { setName(""); setSlug(""); setSlugTouched(false); setError(null); setChecked(false); } }, [open]);

  const effectiveSlug = slugTouched ? slug : slugify(name);
  const nameOk = name.trim().length > 0;
  const slugOk = SLUG_RE.test(effectiveSlug);
  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setChecked(true);
    if (!nameOk || !slugOk) return;
    setBusy(true);
    setError(null);
    try {
      onCreated(await createOrganization({ name: name.trim(), slug: effectiveSlug }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const formId = "create-org-form";
  return (
    <Dialog open={open} title={t("organizations.admin.createTitle")} description={t("organizations.admin.createHint")} onClose={onClose} busy={busy}
      footer={
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>{t("lms.common.cancel")}</Button>
          <Button type="submit" form={formId} loading={busy}>{t("organizations.admin.create")}</Button>
        </>
      }>
      <form id={formId} onSubmit={submit} noValidate className="space-y-4">
        <Input label={t("organizations.fields.name")} value={name} maxLength={200} disabled={busy}
          error={checked && !nameOk ? t("organizations.fields.nameMissing") : undefined} onChange={(e) => setName(e.target.value)} />
        <Input label={t("organizations.fields.slug")} value={effectiveSlug} maxLength={64} disabled={busy} className="font-mono"
          error={checked && !slugOk ? t("organizations.fields.slugHint") : undefined} hint={checked && !slugOk ? undefined : t("organizations.fields.slugHint")}
          onChange={(e) => { setSlugTouched(true); setSlug(e.target.value.toLowerCase()); }} />
        <OrgError error={error} />
      </form>
    </Dialog>
  );
}
