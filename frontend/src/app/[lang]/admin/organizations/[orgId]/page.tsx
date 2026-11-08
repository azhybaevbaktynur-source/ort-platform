"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ExternalLink, Info, TriangleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listAuditLog } from "@/lib/lms/admin";
import {
  SLUG_RE, getOrganization, getOrganizationUsage, getOrgSettings, listOrganizationCourses, listOrganizationStudents,
  listPlatformDepartments, resumeOrganization, suspendOrganization, updateOrganization, type DepartmentOut,
  type DepartmentUsageOut, type OrganizationAdminRowOut, type OrganizationOut, type OrganizationSuspendOut, type OrgSettingsViewOut, type OrgStudentOut,
  type TreeUsageOut,
} from "@/lib/lms/organizations";
import type { CourseStatus } from "@/lib/lms/types";
import { fmtApiDate, fmtApiDateTimeShort } from "@/lib/format";
import { formatBytes } from "@/lib/lms/storage"; // Phase 6b S11b (UX 10): the localized formatter
import {
  Button, Card, Dialog, EmptyState, FilterBar, Input, LinkButton, LoadingState, PageHeader, ReasonDialog, STAFF_WIDTH, Select,
  StatTile, TabPanel, Table, Tabs, cn, toast, type MenuGroup, type TableColumn,
} from "@/components/ui";
import { AuditTable } from "@/components/lms/admin/AuditTable";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useCursorList, useDebounced } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { OrgCourseList } from "@/components/lms/org/OrgCourseList";
import { OrgMembersTab } from "@/components/lms/org/admin/OrgMembersTab";
import { OrgTemplatesTab } from "@/components/lms/org/admin/OrgTemplatesTab";
import { OrgSettingsForm } from "@/components/lms/org/OrgSettingsForm";
import { LoadError, OrgBadge, OrgError, OrgKindBadge } from "@/components/lms/org/OrgUi";
import { DepartmentTree, type DepartmentAction } from "@/components/lms/org/DepartmentTree"; // Phase 9 S2

// Item 4 (ADMIN_ORGS_DESIGN §2.6): + Students and Settings; Summary shows the subtree roll-up and the departments
const TABS = ["summary", "admins", "teachers", "courses", "students", "departments", "templates", "settings", "log"] as const;
type Tab = (typeof TABS)[number];

export default function AdminOrganizationDetailPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const [org, setOrg] = useState<OrganizationAdminRowOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tab, setTab] = useState<Tab>("summary");
  const [usage, setUsage] = useState<TreeUsageOut | null>(null);
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
      setOrg({ ...org, ...organizationFields(updated) });
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
  // the "⋯" menu: Edit, then Suspend / Resume (never for the platform organization: D-ORG-1)
  const overflow: MenuGroup[] = [
    { id: "edit", items: [{ id: "edit", label: t("organizations.admin.edit") }] },
    {
      id: "status", items: org.is_protected ? [] : [suspended
        ? { id: "resume", label: t("organizations.admin.resume") }
        : { id: "suspend", label: t("organizations.admin.suspend"), danger: true }],
    },
  ];
  const onOverflow = (id: string) => {
    if (id === "edit") setEditing(true);
    else { setDialogError(null); setStatusDialog(true); }
  };
  const deptColumns: TableColumn<DepartmentUsageOut>[] = [
    { key: "name", header: t("departments.usageDepartment"), primary: true, cell: (d) => <span className="break-words font-medium">{d.name}</span> },
    { key: "courses", header: t("organizations.counts.courses"), align: "right", cell: (d) => d.courses },
    { key: "teachers", header: t("organizations.counts.teachers"), align: "right", cell: (d) => d.teachers },
    { key: "students", header: t("organizations.counts.students"), align: "right", cell: (d) => d.students },
  ];
  return (
    <div className={cn("w-full", STAFF_WIDTH.list)}>
      <PageHeader
        title={org.name}
        description={org.slug}
        badge={<><OrgKindBadge kind={org.kind} /><OrgBadge tone={org.status} labelKey={`organizations.status.${org.status}`} /></>}
        breadcrumbs={crumbs(orgsCrumb, { label: org.name })}
        primaryAction={
          // ADMIN_ORGS_DESIGN §2.4: navigation only; the server decides from users.is_platform_admin on every request
          <LinkButton href={`/${lang}/org/${org.id}`} variant="secondary" leftIcon={<ExternalLink aria-hidden="true" className="h-4 w-4" />}>
            {t("organizations.admin.openAsOrgAdmin")}
          </LinkButton>
        }
        overflow={overflow}
        onOverflow={onOverflow}
        overflowLabel={t("coursePage.moreActions")}
      />
      {org.is_protected && (
        <p role="note" className="mb-4 flex gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-700">
          <Info aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-slate-500" />
          <span className="min-w-0 break-words">{t("organizations.admin.protectedNote")}</span>
        </p>
      )}
      {suspended && org.suspended_reason && (
        <p role="status" className="mb-4 flex gap-3 rounded-2xl border border-warning-200 bg-warning-50 p-3 text-sm leading-6 text-warning-900">
          <TriangleAlert aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
          <span className="min-w-0 break-words">{t("organizations.admin.suspendedReason", { reason: org.suspended_reason })}</span>
        </p>
      )}

      <Tabs id={tabsId} label={t("organizations.admin.tabsLabel")} value={tab} onChange={(v) => setTab(v as Tab)}
        items={TABS.map((k) => ({ id: k, label: t(`organizations.admin.tabs.${k}`) }))} />
      <TabPanel tabsId={tabsId} value={tab}>
        {tab === "summary" && (
          <div className="space-y-4">
            {usageError ? <LoadError error={usageError} onRetry={loadUsage} /> : null}
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <StatTile size="sm" label={t("organizations.counts.orgAdmins")} value={usage ? usage.org_admins : dash(org.org_admins)} />
              <StatTile size="sm" label={t("organizations.counts.teachers")} value={usage ? usage.teachers : dash(org.teachers)} />
              <StatTile size="sm" label={t("organizations.counts.courses")} value={usage ? usage.courses : dash(org.courses)} />
              <StatTile size="sm" label={t("organizations.counts.students")} value={usage ? usage.students : dash(org.students)} />
              <StatTile size="sm" label={t("organizations.usage.banks")} value={usage ? usage.banks : "—"} />
              <StatTile size="sm" label={t("organizations.usage.questions")} value={usage ? usage.questions : "—"} />
              <div title={t("organizations.usage.storageNote")}>
                <StatTile size="sm" className="h-full" label={t("organizations.usage.storage")} value={bytes(usage ? usage.storage_bytes : org.storage_bytes)} />
              </div>
              <StatTile size="sm" label={t("organizations.admin.created")} value={<span className="text-base font-semibold">{fmtApiDateTimeShort(org.created_at, lang)}</span>} />
            </div>
            {usage && usage.by_department.length > 0 && (
              <Card title={t("departments.usageTitle")} headingLevel={2} padding="none">
                <Table columns={deptColumns} rows={usage.by_department} rowKey={(d) => d.id} caption={t("departments.usageTitle")} density="compact" />
              </Card>
            )}
          </div>
        )}
        {tab === "admins" && <OrgMembersTab org={org} role="org_admin" onChanged={() => void load()} />}
        {tab === "teachers" && <OrgMembersTab org={org} role="teacher" onChanged={() => void load()} />}
        {tab === "courses" && <OrgCoursesTab org={org} />}
        {tab === "students" && <OrgStudentsTab org={org} />}
        {tab === "departments" && <OrgDepartmentsTab org={org} />}
        {tab === "templates" && <OrgTemplatesTab org={org} />}
        {tab === "settings" && <OrgSettingsTab org={org} onSaved={() => void load()} />}
        {tab === "log" && <OrgLogTab org={org} />}
      </TabPanel>

      <EditOrganizationDialog open={editing} org={org} onClose={() => setEditing(false)}
        onSaved={(o) => { setOrg({ ...org, ...o }); setEditing(false); toast.success(t("organizations.admin.saved")); }} />
      <ReasonDialog
        open={statusDialog}
        title={t(suspended ? "organizations.admin.resumeTitle" : "organizations.admin.suspendTitle")}
        object={org.name}
        effect={
          <>
            <p>{t(suspended ? "organizations.admin.resumeBody" : "organizations.admin.suspendBody")}</p>
            {/* item 4: the subtree counts of the row, before the confirm */}
            <p className="mt-2 font-medium text-slate-900">
              {t("organizations.admin.affected", { courses: org.courses, students: org.students, departments: org.departments })}
            </p>
          </>
        }
        confirmLabel={t(suspended ? "organizations.admin.resume" : "organizations.admin.suspend")}
        tone={suspended ? "primary" : "danger"} busy={busy}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(r) => void toggleStatus(r)} onCancel={() => setStatusDialog(false)}
      />
    </div>
  );
}

/** The organization of a suspend/resume answer, without its `affected` counts (the row keeps its own). */
function organizationFields(o: OrganizationSuspendOut): OrganizationOut {
  const copy: Partial<OrganizationSuspendOut> = { ...o };
  delete copy.affected;
  return copy as OrganizationOut;
}

// --- Phase 9 S2 begin --- (PHASE_9_DESIGN 8.1: Departments tab with suspend / resume)
function OrgDepartmentsTab({ org }: { org: OrganizationOut }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<DepartmentOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [target, setTarget] = useState<{ dept: DepartmentOut; action: "suspend" | "resume" } | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      setRows(await listPlatformDepartments(org.id));
    } catch (e) {
      setError(e);
    }
  }, [org.id]);
  useEffect(() => { void load(); }, [load]);

  const onAction = (action: DepartmentAction, dept: DepartmentOut) => {
    if (action !== "suspend" && action !== "resume") return;
    setDialogError(null);
    setTarget({ dept, action });
  };
  const confirm = async (reason: string) => {
    if (!target) return;
    setBusy(true);
    setDialogError(null);
    try {
      if (target.action === "suspend") await suspendOrganization(target.dept.id, reason);
      else await resumeOrganization(target.dept.id, reason);
      toast.success(t(target.action === "suspend" ? "departments.suspendedToast" : "departments.resumedToast", { name: target.dept.name }));
      setTarget(null);
      await load();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };

  if (error && !rows) return <LoadError error={error} onRetry={load} />;
  if (!rows) return <LoadingState label={t("lms.common.loading")} />;
  const suspend = target?.action === "suspend";
  return (
    <div className="space-y-3">
      <DepartmentTree rows={rows} mode="platform" onAction={onAction} />
      {rows.length <= 1 && <EmptyState variant="plain" className="py-4" title={t("departments.noneUsage")} />}
      <ReasonDialog
        open={!!target}
        title={t(suspend ? "departments.suspendTitle" : "departments.resumeTitle")}
        object={target?.dept.name}
        effect={t(suspend ? "departments.suspendBody" : "departments.resumeBody")}
        confirmLabel={t(suspend ? "organizations.admin.suspend" : "organizations.admin.resume")}
        tone={suspend ? "danger" : "primary"} busy={busy}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(r) => void confirm(r)} onCancel={() => setTarget(null)}
      />
    </div>
  );
}
// --- Phase 9 S2 end ---

const COURSE_STATUSES: (CourseStatus | "")[] = ["", "draft", "published", "concluded"];

function OrgCoursesTab({ org }: { org: OrganizationOut }) {
  const { lang, t } = useTranslation();
  const [input, setInput] = useState("");
  const q = useDebounced(input);
  const [status, setStatus] = useState<CourseStatus | "">("");
  const fetchPage = useCallback((cursor: string | null) => listOrganizationCourses(org.id, { q, status, cursor }), [org.id, q, status]);
  const list = useCursorList(fetchPage);
  const state = useTableState(list);
  const filtered = !!(q || status);
  return (
    <>
      <OrgCourseList courses={list.items} hrefFor={(c) => `/${lang}/admin/courses/${c.id}`} {...state}
        search={
          <FilterBar
            search={{ value: input, onChange: setInput, label: t("lms.common.search"), placeholder: t("organizations.admin.courses.searchPlaceholder") }}
            canReset={filtered} onReset={() => { setInput(""); setStatus(""); }}
          >
            <Select label={t("platformAdmin.courses.status")} value={status} onChange={(e) => setStatus(e.target.value as CourseStatus | "")}
              options={COURSE_STATUSES.map((s) => ({ value: s, label: s ? t(`courses.status.${s}`) : t("organizations.admin.courses.anyStatus") }))} />
          </FilterBar>
        }
        empty={<EmptyState variant="plain" title={filtered ? t("organizations.admin.emptySearch") : t("organizations.courses.empty")} />} />
      <MoreError list={list} />
    </>
  );
}

/** Item 4 (D-ORG-4): the subtree's students, name, email and counts only; the person page has the rest. */
function OrgStudentsTab({ org }: { org: OrganizationOut }) {
  const { lang, t } = useTranslation();
  const [input, setInput] = useState("");
  const q = useDebounced(input);
  const fetchPage = useCallback((cursor: string | null) => listOrganizationStudents(org.id, { q, cursor }), [org.id, q]);
  const list = useCursorList(fetchPage);
  const state = useTableState(list);
  const date = (v: string | null) => (v ? fmtApiDate(v, lang) : "—");
  const columns: TableColumn<OrgStudentOut>[] = [
    {
      key: "person", header: t("organizations.admin.students.person"), primary: true,
      cell: (s) => (
        <>
          <Link href={`/${lang}/admin/users/${s.user.id}`} className="break-words font-semibold text-brand-700 hover:underline">{s.user.display_name || s.user.email}</Link>
          <span className="block break-all text-xs font-normal text-slate-600">{s.user.email}</span>
        </>
      ),
    },
    { key: "courses", header: t("organizations.admin.students.courses"), align: "right", cell: (s) => s.courses },
    { key: "first", header: t("organizations.admin.students.firstEnrolled"), nowrap: true, hideOnMobile: true, cell: (s) => date(s.first_enrolled_at) },
    { key: "last", header: t("organizations.admin.students.lastEnrolled"), nowrap: true, cell: (s) => date(s.last_active_enrollment_at) },
  ];
  return (
    <>
      <Table
        caption={t("organizations.admin.tabs.students")}
        columns={columns}
        rows={list.items}
        rowKey={(s) => s.user.id}
        density="compact"
        {...state}
        search={
          <div className="space-y-2">
            <FilterBar search={{ value: input, onChange: setInput, label: t("lms.common.search"), placeholder: t("organizations.admin.students.searchPlaceholder") }}
              canReset={!!q} onReset={() => setInput("")} />
            <p className="text-xs leading-5 text-slate-600">{t("organizations.admin.students.note")}</p>
          </div>
        }
        empty={<EmptyState variant="plain" title={q ? t("organizations.admin.students.emptySearch") : t("organizations.admin.students.empty")} />}
      />
      <MoreError list={list} />
    </>
  );
}

/**
 * Item 4: the same form as `/org/{id}/settings`, saved through `PATCH /platform/organizations/{id}` (audited as the
 * platform admin). A department shows its root's settings read-only with the reason (the form's own note).
 */
function OrgSettingsTab({ org, onSaved }: { org: OrganizationOut; onSaved: () => void }) {
  const { t } = useTranslation();
  const [view, setView] = useState<OrgSettingsViewOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      setView(await getOrgSettings(org.id));
    } catch (e) {
      setError(e);
    }
  }, [org.id]);
  useEffect(() => { void load(); }, [load]);
  if (error && !view) return <LoadError error={error} onRetry={load} />;
  if (!view) return <LoadingState label={t("lms.common.loading")} />;
  return (
    <div className={STAFF_WIDTH.form}>
      <OrgSettingsForm view={view} readOnly={false} onSaved={(v) => { setView(v); onSaved(); }}
        submit={async (settings) => {
          await updateOrganization(view.root_id, { settings });
          return getOrgSettings(org.id);
        }} />
    </div>
  );
}

function OrgLogTab({ org }: { org: OrganizationOut }) {
  const { lang, t } = useTranslation();
  const fetchPage = useCallback((cursor: string | null) => listAuditLog({ target_type: "organization", target_id: org.id, cursor }), [org.id]);
  const list = useCursorList(fetchPage);
  const state = useTableState(list);
  return (
    <div className="space-y-3">
      <Link href={`/${lang}/admin/audit-log`} className="inline-flex min-h-11 items-center text-sm font-medium text-brand-700 hover:underline sm:min-h-0">{t("organizations.admin.logAll")}</Link>
      <AuditTable entries={list.items} {...state} empty={<EmptyState title={t("platformAdmin.audit.empty")} />} />
      <MoreError list={list} />
    </div>
  );
}

/** Name and short name; the settings live on the Settings tab. The platform organization's slug is fixed. */
function EditOrganizationDialog({ open, org, onClose, onSaved }: { open: boolean; org: OrganizationAdminRowOut; onClose: () => void; onSaved: (o: OrganizationOut) => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState(org.name);
  const [slug, setSlug] = useState(org.slug);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    if (open) { setName(org.name); setSlug(org.slug); setError(null); setChecked(false); }
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
      onSaved(await updateOrganization(org.id, { name: name.trim(), ...(org.is_protected ? {} : { slug }) }));
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
        <Input label={t("organizations.fields.slug")} value={slug} maxLength={64} disabled={busy || org.is_protected} className="font-mono"
          error={checked && !slugOk ? t("organizations.fields.slugEditHint") : undefined}
          hint={org.is_protected ? t("organizations.errors.platform_org_protected") : checked && !slugOk ? undefined : t("organizations.fields.slugEditHint")}
          onChange={(e) => setSlug(e.target.value.toLowerCase())} />
        <OrgError error={error} />
      </form>
    </Dialog>
  );
}
