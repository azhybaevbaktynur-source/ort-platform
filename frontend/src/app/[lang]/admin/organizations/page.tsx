"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  SLUG_RE, createOrganization, listOrganizations, slugify, type OrganizationAdminRowOut, type OrganizationOut, type OrgListSort,
  type OrgRootKind, type OrgStatus,
} from "@/lib/lms/organizations";
import { fmtApiDate } from "@/lib/format";
import { formatBytes } from "@/lib/lms/storage";
import { Button, Dialog, EmptyState, FilterBar, Input, PageHeader, STAFF_WIDTH, Select, Table, cn, type TableColumn } from "@/components/ui";
import { OrgBadge, OrgError, OrgKindBadge } from "@/components/lms/org/OrgUi";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useCursorList, useDebounced } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";

const STATUSES: (OrgStatus | "")[] = ["", "active", "suspended"];
// item 4: roots only, departments live inside; step 3b S3: schools and the platform only (independent teachers' own
// spaces are never organizations here: Admin → Преподаватели lists them)
const KINDS: (OrgRootKind | "")[] = ["", "school", "platform"];
const SORTS: OrgListSort[] = ["created_desc", "name_asc"];

export default function AdminOrganizationsPage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const crumbs = useAdminCrumbs();
  const [input, setInput] = useState("");
  const q = useDebounced(input);
  const [status, setStatus] = useState<OrgStatus | "">("");
  const [kind, setKind] = useState<OrgRootKind | "">("");
  const [sort, setSort] = useState<OrgListSort>("created_desc");
  const [creating, setCreating] = useState(false);
  const fetchPage = useCallback((cursor: string | null) => listOrganizations({ q, status, kind, sort, cursor }), [q, status, kind, sort]);
  const list = useCursorList(fetchPage);
  const state = useTableState(list);

  const n = (v: number | undefined) => (typeof v === "number" ? v : "—");
  const units: [string, string, string, string] = [t("storage.units.b"), t("storage.units.kb"), t("storage.units.mb"), t("storage.units.gb")];
  const columns: TableColumn<OrganizationAdminRowOut>[] = [
    {
      key: "name", header: t("organizations.fields.name"), primary: true,
      cell: (o) => (
        <>
          <Link href={`/${lang}/admin/organizations/${o.id}`} className="break-words font-semibold text-brand-700 hover:underline">{o.name}</Link>
          <span className="block break-all text-xs font-normal text-slate-600">
            {o.slug}{o.departments > 0 ? ` · ${t("organizations.admin.departmentsCount", { n: o.departments })}` : ""}
          </span>
        </>
      ),
    },
    { key: "kind", header: t("organizations.admin.kind"), cell: (o) => <OrgKindBadge kind={o.kind} /> },
    { key: "status", header: t("organizations.admin.status"), cell: (o) => <OrgBadge tone={o.status} labelKey={`organizations.status.${o.status}`} /> },
    { key: "teachers", header: t("organizations.counts.teachers"), align: "right", hideOnMobile: true, cell: (o) => n(o.teachers) },
    { key: "courses", header: t("organizations.counts.courses"), align: "right", cell: (o) => n(o.courses) },
    { key: "students", header: t("organizations.counts.students"), align: "right", cell: (o) => n(o.students) },
    {
      // owner-based estimate (ADMIN_ORGS_DESIGN §2.1): the header carries the note as a tooltip
      key: "storage", header: <span title={t("organizations.usage.storageNote")}>{t("organizations.usage.storage")}</span>,
      label: t("organizations.usage.storage"), align: "right", nowrap: true, hideOnMobile: true,
      cell: (o) => formatBytes(o.storage_bytes ?? 0, lang, units),
    },
    { key: "created", header: t("organizations.admin.created"), nowrap: true, hideOnMobile: true, cell: (o) => fmtApiDate(o.created_at, lang) },
  ];
  const filtered = !!(q || status || kind);
  return (
    <div className={cn("w-full", STAFF_WIDTH.list)}>
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
        density="compact"
        {...state}
        search={
          <FilterBar
            search={{ value: input, onChange: setInput, label: t("lms.common.search"), placeholder: t("organizations.admin.searchPlaceholder") }}
            canReset={filtered} onReset={() => { setInput(""); setStatus(""); setKind(""); }}
          >
            <Select label={t("organizations.admin.kind")} value={kind} onChange={(e) => setKind(e.target.value as OrgRootKind | "")}
              options={KINDS.map((k) => ({ value: k, label: k ? t(`organizations.kind.${k}`) : t("organizations.admin.anyKind") }))} />
            <Select label={t("organizations.admin.status")} value={status} onChange={(e) => setStatus(e.target.value as OrgStatus | "")}
              options={STATUSES.map((s) => ({ value: s, label: s ? t(`organizations.status.${s}`) : t("organizations.admin.anyStatus") }))} />
            <Select label={t("organizations.admin.sort")} value={sort} onChange={(e) => setSort(e.target.value as OrgListSort)}
              options={SORTS.map((s) => ({ value: s, label: t(s === "name_asc" ? "organizations.admin.sortName" : "organizations.admin.sortCreated") }))} />
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
