"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { TriangleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listAuditLog } from "@/lib/lms/admin";
import {
  SLUG_RE, getOrganization, getOrganizationUsage, listOrganizationCourses, resumeOrganization,
  suspendOrganization, updateOrganization, type OrganizationAdminRowOut, type OrganizationOut, type OrgUsageOut,
} from "@/lib/lms/organizations";
import { fmtApiDateTimeShort } from "@/lib/format";
import { formatBytes } from "@/lib/lms/storage"; // Phase 6b S11b (UX 10): the localized formatter
import {
  Button, Card, Checkbox, DescriptionList, Dialog, EmptyState, Input, LoadingState, PageHeader, ReasonDialog, StatTile, TabPanel, Tabs, toast,
} from "@/components/ui";
import { AuditTable } from "@/components/lms/admin/AuditTable";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { OrgCourseList } from "@/components/lms/org/OrgCourseList";
import { OrgMembersTab } from "@/components/lms/org/admin/OrgMembersTab";
import { OrgTemplatesTab } from "@/components/lms/org/admin/OrgTemplatesTab";
import { LoadError, OrgBadge, OrgError } from "@/components/lms/org/OrgUi";

const TABS = ["summary", "admins", "teachers", "courses", "usage", "templates", "log"] as const;
type Tab = (typeof TABS)[number];

export default function AdminOrganizationDetailPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const [org, setOrg] = useState<OrganizationAdminRowOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tab, setTab] = useState<Tab>("summary");
  const [usage, setUsage] = useState<OrgUsageOut | null>(null);
  const [usageError, setUsageError] = useState<unknown>(null);
  const [editing, setEditing] = useState(false);
  const [statusDialog, setStatusDialog] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setOrg(await getOrganization(orgId));
    } catch (e) {
      setError(e);
    }
  }, [orgId]);
  const loadUsage = useCallback(async () => {
    setUsageError(null);
    try {
      setUsage(await getOrganizationUsage(orgId));
    } catch (e) {
      setUsageError(e);
    }
  }, [orgId]);
  useEffect(() => { void load(); void loadUsage(); }, [load, loadUsage]);

  const orgsCrumb = { label: t("organizations.admin.title"), href: `/${lang}/admin/organizations` };
  if (error && !org) {
    return (
      <div>
        <PageHeader title={t("organizations.admin.title")} breadcrumbs={crumbs(orgsCrumb, { label: "…" })} />
        <LoadError error={error} onRetry={load} />
      </div>
    );
  }
  if (!org) return <LoadingState label={t("lms.common.loading")} />;

  const suspended = org.status === "suspended";
  const toggleStatus = async (reason: string) => {
    setBusy(true);
    setDialogError(null);
    try {
      const updated = suspended ? await resumeOrganization(org.id, reason) : await suspendOrganization(org.id, reason);
      setOrg({ ...org, ...updated });
      toast.success(t(suspended ? "organizations.admin.resumed" : "organizations.admin.suspended", { org: org.name }));
      setStatusDialog(false);
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };

  const tabsId = "org-detail";
  const units: [string, string, string, string] = [t("storage.units.b"), t("storage.units.kb"), t("storage.units.mb"), t("storage.units.gb")];
  const bytes = (n: number | null | undefined) => (n === null || n === undefined || !Number.isFinite(n) ? "—" : formatBytes(n, lang, units));
  const dash = (v: React.ReactNode) => (v === undefined || v === null || v === "" ? "—" : v);
  return (
    <div>
      <PageHeader
        title={org.name}
        description={org.slug}
        badge={<OrgBadge tone={org.status} labelKey={`organizations.status.${org.status}`} />}
        breadcrumbs={crumbs(orgsCrumb, { label: org.name })}
        secondaryActions={
          <>
            <Button variant="secondary" onClick={() => setEditing(true)}>{t("organizations.admin.edit")}</Button>
            <Button variant={suspended ? "secondary" : "dangerOutline"} onClick={() => { setDialogError(null); setStatusDialog(true); }}>
              {t(suspended ? "organizations.admin.resume" : "organizations.admin.suspend")}
            </Button>
          </>
        }
      />
      {suspended && org.suspended_reason && (
        <p role="status" className="mb-4 flex gap-3 rounded-2xl border border-warning-200 bg-warning-50 p-4 text-sm leading-6 text-warning-900">
          <TriangleAlert aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
          <span className="min-w-0 break-words">{t("organizations.admin.suspendedReason", { reason: org.suspended_reason })}</span>
        </p>
      )}

      <Tabs id={tabsId} label={t("organizations.admin.tabsLabel")} value={tab} onChange={(v) => setTab(v as Tab)}
        items={TABS.map((k) => ({ id: k, label: t(`organizations.admin.tabs.${k}`) }))} />
      <TabPanel tabsId={tabsId} value={tab}>
        {tab === "summary" && (
          <Card>
            <DescriptionList twoColumns items={[
              { key: "admins", term: t("organizations.counts.orgAdmins"), description: dash(org.org_admins) },
              { key: "teachers", term: t("organizations.counts.teachers"), description: dash(org.teachers) },
              { key: "courses", term: t("organizations.counts.courses"), description: dash(org.courses) },
              { key: "storage", term: t("organizations.usage.storage"), description: usage ? bytes(usage.storage_bytes) : "—" },
              { key: "created", term: t("organizations.admin.created"), description: fmtApiDateTimeShort(org.created_at, lang) },
              { key: "canCreate", term: t("organizations.fields.teachersCanCreate"), description: org.settings?.teachers_can_create_courses ? t("platformAdmin.yes") : t("platformAdmin.no") },
            ]} />
          </Card>
        )}
        {tab === "admins" && <OrgMembersTab org={org} role="org_admin" onChanged={() => void load()} />}
        {tab === "teachers" && <OrgMembersTab org={org} role="teacher" onChanged={() => void load()} />}
        {tab === "courses" && <OrgCoursesTab org={org} />}
        {tab === "usage" && (
          usageError ? <LoadError error={usageError} onRetry={loadUsage} /> : !usage ? <LoadingState label={t("lms.common.loading")} /> : (
            <div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <StatTile label={t("organizations.counts.teachers")} value={usage.teachers} />
                <StatTile label={t("organizations.counts.courses")} value={usage.courses} />
                <StatTile label={t("organizations.counts.students")} value={usage.students} />
                <StatTile label={t("organizations.usage.banks")} value={usage.banks} />
                <StatTile label={t("organizations.usage.questions")} value={usage.questions} />
                <StatTile label={t("organizations.usage.storage")} value={bytes(usage.storage_bytes)} />
              </div>
              <p className="mt-3 text-sm text-slate-600">{t("organizations.usage.storageNote")}</p>
            </div>
          )
        )}
        {tab === "templates" && <OrgTemplatesTab org={org} />}
        {tab === "log" && <OrgLogTab org={org} />}
      </TabPanel>

      <EditOrganizationDialog open={editing} org={org} onClose={() => setEditing(false)}
        onSaved={(o) => { setOrg({ ...org, ...o }); setEditing(false); toast.success(t("organizations.admin.saved")); }} />
      <ReasonDialog
        open={statusDialog}
        title={t(suspended ? "organizations.admin.resumeTitle" : "organizations.admin.suspendTitle")}
        object={org.name}
        effect={t(suspended ? "organizations.admin.resumeBody" : "organizations.admin.suspendBody")}
        confirmLabel={t(suspended ? "organizations.admin.resume" : "organizations.admin.suspend")}
        tone={suspended ? "primary" : "danger"} busy={busy}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(r) => void toggleStatus(r)} onCancel={() => setStatusDialog(false)}
      />
    </div>
  );
}

function OrgCoursesTab({ org }: { org: OrganizationOut }) {
  const { lang, t } = useTranslation();
  const fetchPage = useCallback((cursor: string | null) => listOrganizationCourses(org.id, { cursor }), [org.id]);
  const list = useCursorList(fetchPage);
  const state = useTableState(list);
  return (
    <>
      <OrgCourseList courses={list.items} hrefFor={(c) => `/${lang}/admin/courses/${c.id}`} {...state}
        empty={<EmptyState title={t("organizations.courses.empty")} />} />
      <MoreError list={list} />
    </>
  );
}

function OrgLogTab({ org }: { org: OrganizationOut }) {
  const { lang, t } = useTranslation();
  const fetchPage = useCallback((cursor: string | null) => listAuditLog({ target_type: "organization", target_id: org.id, cursor }), [org.id]);
  const list = useCursorList(fetchPage);
  const state = useTableState(list);
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-700">
        {t("organizations.admin.logIntro")}{" "}
        <Link href={`/${lang}/admin/audit-log`} className="font-medium text-brand-700 hover:underline">{t("organizations.admin.logAll")}</Link>
      </p>
      <AuditTable entries={list.items} {...state} empty={<EmptyState title={t("platformAdmin.audit.empty")} />} />
      <MoreError list={list} />
    </div>
  );
}

function EditOrganizationDialog({ open, org, onClose, onSaved }: { open: boolean; org: OrganizationOut; onClose: () => void; onSaved: (o: OrganizationOut) => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState(org.name);
  const [slug, setSlug] = useState(org.slug);
  const [canCreate, setCanCreate] = useState(!!org.settings?.teachers_can_create_courses);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    if (open) { setName(org.name); setSlug(org.slug); setCanCreate(!!org.settings?.teachers_can_create_courses); setError(null); setChecked(false); }
  }, [open, org]);
  const nameOk = name.trim().length > 0;
  const slugOk = SLUG_RE.test(slug);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setChecked(true);
    if (!nameOk || !slugOk) return;
    setBusy(true);
    setError(null);
    try {
      const o = await updateOrganization(org.id, {
        name: name.trim(), slug, settings: { teachers_can_create_courses: canCreate },
      });
      onSaved(o);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const formId = "edit-org-form";
  return (
    <Dialog open={open} title={t("organizations.admin.editTitle")} onClose={onClose} busy={busy}
      footer={
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>{t("lms.common.cancel")}</Button>
          <Button type="submit" form={formId} loading={busy}>{t("lms.common.save")}</Button>
        </>
      }>
      <form id={formId} onSubmit={submit} noValidate className="space-y-4">
        <Input label={t("organizations.fields.name")} value={name} maxLength={200} disabled={busy}
          error={checked && !nameOk ? t("organizations.fields.nameMissing") : undefined} onChange={(e) => setName(e.target.value)} />
        <Input label={t("organizations.fields.slug")} value={slug} maxLength={64} disabled={busy} className="font-mono"
          error={checked && !slugOk ? t("organizations.fields.slugEditHint") : undefined} hint={checked && !slugOk ? undefined : t("organizations.fields.slugEditHint")}
          onChange={(e) => setSlug(e.target.value.toLowerCase())} />
        <Checkbox label={t("organizations.fields.teachersCanCreate")} hint={t("organizations.fields.teachersCanCreateHint")}
          checked={canCreate} disabled={busy} onChange={(e) => setCanCreate(e.target.checked)} />
        <OrgError error={error} />
      </form>
    </Dialog>
  );
}
