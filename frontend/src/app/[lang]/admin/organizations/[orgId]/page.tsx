"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { listAuditLog } from "@/lib/lms/admin";
import {
  SLUG_RE, formatBytes, getOrganization, getOrganizationUsage, listOrganizationCourses, resumeOrganization,
  suspendOrganization, updateOrganization, type OrganizationAdminRowOut, type OrganizationOut, type OrgCourseOut, type OrgUsageOut,
} from "@/lib/lms/organizations";
import type { AuditEntryOut } from "@/lib/lms/types";
import { fmtApiDateTime } from "@/lib/format";
import { Modal } from "@/components/lms/assessments/Modal";
import { Pager } from "@/components/lms/Pager";
import { AuditTable } from "@/components/lms/admin/AuditTable";
import { ReasonDialog } from "@/components/lms/admin/ReasonDialog";
import { OrgCourseList } from "@/components/lms/org/OrgCourseList";
import { OrgMembersTab } from "@/components/lms/org/admin/OrgMembersTab";
import { OrgTemplatesTab } from "@/components/lms/org/admin/OrgTemplatesTab";
import { EmptyBox, Loading, OrgBadge, OrgError, btn, cardCls, inputCls, labelCls } from "@/components/lms/org/OrgUi";
import { toast } from "@/components/ui/Toast";

const TABS = ["summary", "admins", "teachers", "courses", "usage", "templates", "log"] as const;
type Tab = (typeof TABS)[number];

export default function AdminOrganizationDetailPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { lang, t } = useTranslation();
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

  const back = <Link href={`/${lang}/admin/organizations`} className="text-sm font-medium text-brand-700 hover:underline">{t("organizations.admin.back")}</Link>;
  if (error && !org) return <div className="space-y-3">{back}<OrgError error={error} onRetry={load} /></div>;
  if (!org) return <Loading />;

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

  const tabId = (k: Tab) => `org-tab-${k}`;
  return (
    <div>
      {back}
      <div className="mb-1 mt-2 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-slate-900">{org.name}</h1>
        <OrgBadge tone={org.status} labelKey={`organizations.status.${org.status}`} />
      </div>
      <p className="mb-4 text-sm text-slate-500">{org.slug}</p>
      {suspended && org.suspended_reason && (
        <p role="status" className="mb-4 rounded-2xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {t("organizations.admin.suspendedReason", { reason: org.suspended_reason })}
        </p>
      )}
      <div className="mb-6 flex flex-wrap gap-2">
        <button type="button" className={btn.secondary} onClick={() => setEditing(true)}>{t("organizations.admin.edit")}</button>
        <button type="button" className={suspended ? btn.secondary : btn.danger} onClick={() => { setDialogError(null); setStatusDialog(true); }}>
          {t(suspended ? "organizations.admin.resume" : "organizations.admin.suspend")}
        </button>
      </div>

      <div role="tablist" aria-label={t("organizations.admin.tabsLabel")} className="mb-4 flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((k) => (
          <button key={k} id={tabId(k)} type="button" role="tab" aria-selected={tab === k} aria-controls={`${tabId(k)}-panel`}
            onClick={() => setTab(k)}
            className={`min-h-[44px] rounded-t-lg px-3 text-sm font-medium ${tab === k ? "border-b-2 border-brand-600 text-brand-700" : "text-slate-600 hover:text-slate-900"}`}>
            {t(`organizations.admin.tabs.${k}`)}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${tabId(tab)}-panel`} aria-labelledby={tabId(tab)}>
        {tab === "summary" && (
          <div className={cardCls}>
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <Fact label={t("organizations.counts.orgAdmins")} value={org.org_admins} />
              <Fact label={t("organizations.counts.teachers")} value={org.teachers} />
              <Fact label={t("organizations.counts.courses")} value={org.courses} />
              <Fact label={t("organizations.usage.storage")} value={usage ? formatBytes(usage.storage_bytes, lang) : undefined} />
              <Fact label={t("organizations.admin.created")} value={fmtApiDateTime(org.created_at, lang)} />
              <Fact label={t("organizations.fields.teachersCanCreate")} value={org.settings?.teachers_can_create_courses ? t("platformAdmin.yes") : t("platformAdmin.no")} />
            </dl>
          </div>
        )}
        {tab === "admins" && <OrgMembersTab org={org} role="org_admin" onChanged={() => void load()} />}
        {tab === "teachers" && <OrgMembersTab org={org} role="teacher" onChanged={() => void load()} />}
        {tab === "courses" && <OrgCoursesTab org={org} />}
        {tab === "usage" && (
          usageError ? <OrgError error={usageError} onRetry={loadUsage} /> : !usage ? <Loading /> : (
            <div className={cardCls}>
              <dl className="grid gap-3 text-sm sm:grid-cols-3">
                <Fact label={t("organizations.counts.teachers")} value={usage.teachers} />
                <Fact label={t("organizations.counts.courses")} value={usage.courses} />
                <Fact label={t("organizations.counts.students")} value={usage.students} />
                <Fact label={t("organizations.usage.banks")} value={usage.banks} />
                <Fact label={t("organizations.usage.questions")} value={usage.questions} />
                <Fact label={t("organizations.usage.storage")} value={formatBytes(usage.storage_bytes, lang)} />
              </dl>
              <p className="mt-3 text-xs text-slate-500">{t("organizations.usage.storageNote")}</p>
            </div>
          )
        )}
        {tab === "templates" && <OrgTemplatesTab org={org} />}
        {tab === "log" && <OrgLogTab org={org} />}
      </div>

      <EditOrganizationDialog open={editing} org={org} onClose={() => setEditing(false)}
        onSaved={(o) => { setOrg({ ...org, ...o }); setEditing(false); toast.success(t("organizations.admin.saved")); }} />
      <ReasonDialog
        open={statusDialog}
        title={t(suspended ? "organizations.admin.resumeTitle" : "organizations.admin.suspendTitle", { org: org.name })}
        body={t(suspended ? "organizations.admin.resumeBody" : "organizations.admin.suspendBody", { org: org.name })}
        confirmLabel={t(suspended ? "organizations.admin.resume" : "organizations.admin.suspend")}
        danger={!suspended} busy={busy} error={dialogError}
        onConfirm={(r) => void toggleStatus(r)} onCancel={() => setStatusDialog(false)}
      />
    </div>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode | undefined }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-900">{value === undefined || value === null || value === "" ? "—" : value}</dd>
    </div>
  );
}

function OrgCoursesTab({ org }: { org: OrganizationOut }) {
  const { lang, t } = useTranslation();
  const [items, setItems] = useState<OrgCourseOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listOrganizationCourses(org.id, { cursor: next });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [org.id]);
  useEffect(() => { void load(); }, [load]);
  if (error) return <OrgError error={error} onRetry={() => load()} />;
  if (loading && items.length === 0) return <Loading />;
  if (items.length === 0) return <EmptyBox text={t("organizations.courses.empty")} />;
  return (
    <div>
      <p className="mb-2 text-xs text-slate-500">{t("organizations.courses.shown", { n: items.length })}</p>
      <OrgCourseList courses={items} hrefFor={(c) => `/${lang}/admin/courses/${c.id}`} />
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
    </div>
  );
}

function OrgLogTab({ org }: { org: OrganizationOut }) {
  const { lang, t } = useTranslation();
  const [items, setItems] = useState<AuditEntryOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listAuditLog({ target_type: "organization", target_id: org.id, cursor: next });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [org.id]);
  useEffect(() => { void load(); }, [load]);
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">
        {t("organizations.admin.logIntro")}{" "}
        <Link href={`/${lang}/admin/audit-log`} className="font-medium text-brand-700 hover:underline">{t("organizations.admin.logAll")}</Link>
      </p>
      {error ? <OrgError error={error} onRetry={() => load()} /> : null}
      {loading && items.length === 0 && !error && <Loading />}
      {!loading && !error && items.length === 0 && <EmptyBox text={t("platformAdmin.audit.empty")} />}
      {items.length > 0 && <AuditTable entries={items} />}
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
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
  return (
    <Modal open={open} title={t("organizations.admin.editTitle", { org: org.name })} onClose={onClose} busy={busy}>
      <form onSubmit={submit} noValidate className="space-y-4">
        <div>
          <label htmlFor="eo-name" className={labelCls}>{t("organizations.fields.name")}</label>
          <input id="eo-name" value={name} maxLength={200} disabled={busy} aria-invalid={checked && !nameOk} onChange={(e) => setName(e.target.value)} className={inputCls} />
          {checked && !nameOk && <p role="alert" className="mt-1 text-xs text-red-700">{t("organizations.fields.nameMissing")}</p>}
        </div>
        <div>
          <label htmlFor="eo-slug" className={labelCls}>{t("organizations.fields.slug")}</label>
          <input id="eo-slug" value={slug} maxLength={64} disabled={busy} aria-invalid={checked && !slugOk}
            onChange={(e) => setSlug(e.target.value.toLowerCase())} className={`${inputCls} font-mono`} />
          <p className={`mt-1 text-xs ${checked && !slugOk ? "text-red-700" : "text-slate-500"}`}>{t("organizations.fields.slugEditHint")}</p>
        </div>
        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input type="checkbox" className="mt-1 h-4 w-4" checked={canCreate} disabled={busy} onChange={(e) => setCanCreate(e.target.checked)} />
          <span>
            <span className="font-medium">{t("organizations.fields.teachersCanCreate")}</span>
            <span className="block text-xs text-slate-500">{t("organizations.fields.teachersCanCreateHint")}</span>
          </span>
        </label>
        <OrgError error={error} />
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btn.secondary} disabled={busy} onClick={onClose}>{t("lms.common.cancel")}</button>
          <button type="submit" className={btn.primary} disabled={busy}>{busy ? t("lms.common.loading") : t("lms.common.save")}</button>
        </div>
      </form>
    </Modal>
  );
}
