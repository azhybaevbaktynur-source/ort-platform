"use client";

// Step 3b S3 (CATALOG_AND_TEACHERS_DESIGN 3.2, owner D9): Admin → Преподаватели, tabs Преподаватели · Заявки. The first
// tab is one list of the people who teach (`GET /platform/teachers`, by name, cursor-paged): independent teachers
// («Независимый преподаватель», never an organization), school teachers and both. The second tab is the teacher
// requests queue (the old /admin/teacher-requests address redirects here with `?tab=requests`). The server decides
// every permission; this page only shows what the platform admin may read.
import React, { Suspense, useCallback, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { listTeachers, type TeacherListKind, type TeacherListStatus } from "@/lib/lms/admin";
import type { TeacherRowOut } from "@/lib/lms/types";
import { fmtApiDate, fmtApiDateTimeShort } from "@/lib/format";
import { EmptyState, FilterBar, PageHeader, STAFF_WIDTH, Select, TabPanel, Table, Tabs, type TableColumn } from "@/components/ui";
import { UserStatusBadge } from "@/components/lms/admin/UserStatusBadge";
import { useAdminCrumbs, useAdminSummary } from "@/components/lms/admin/AdminShell";
import { useCursorList, useDebounced } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { REQUEST_FILTERS, TeacherRequestsPanel, type RequestFilter } from "@/components/lms/admin/TeacherRequestsPanel";
import { useWhereTeaches } from "@/components/lms/admin/TeachingParts";
import { SystemAccountBadge } from "@/components/lms/org/OrgUi";
import { isSystemAccount } from "@/lib/lms/organizations";

type Tab = "teachers" | "requests";
const KINDS: (TeacherListKind | "")[] = ["", "independent", "school"];
const STATUSES: (TeacherListStatus | "")[] = ["", "approved", "revoked"];

function asTab(v: string | null): Tab {
  return v === "requests" ? "requests" : "teachers";
}
function asRequestFilter(v: string | null): RequestFilter {
  return REQUEST_FILTERS.includes(v as RequestFilter) ? (v as RequestFilter) : "pending";
}

function AdminTeachers() {
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const router = useRouter();
  const params = useSearchParams();
  const { pending } = useAdminSummary();
  const [tab, setTabRaw] = useState<Tab>(() => asTab(params.get("tab")));
  const [requestFilter, setRequestFilterRaw] = useState<RequestFilter>(() => asRequestFilter(params.get("status")));
  const go = (next: Tab, filter: RequestFilter) => {
    const q = next === "requests" ? `?tab=requests${filter !== "pending" ? `&status=${filter}` : ""}` : "";
    router.replace(`/${lang}/admin/teachers${q}`, { scroll: false });
  };
  const setTab = (v: Tab) => { setTabRaw(v); go(v, requestFilter); };
  const setRequestFilter = (f: RequestFilter) => { setRequestFilterRaw(f); go(tab, f); };

  const [input, setInput] = useState("");
  const q = useDebounced(input);
  const [kind, setKind] = useState<TeacherListKind | "">("");
  const [status, setStatus] = useState<TeacherListStatus | "">("");
  const fetchPage = useCallback((cursor: string | null) => listTeachers({ q, kind, status, cursor }), [q, kind, status]);
  const list = useCursorList(fetchPage);
  const table = useTableState(list);
  const where = useWhereTeaches();
  const dash = <span className="text-slate-500">—</span>;

  const columns: TableColumn<TeacherRowOut>[] = [
    {
      key: "person", header: t("platformAdmin.teachers.columns.person"), primary: true,
      cell: (r) => (
        <>
          <Link href={`/${lang}/admin/users/${r.user.id}`} className="break-words font-semibold text-brand-700 hover:underline">{r.user.display_name || r.user.email}</Link>
          {isSystemAccount(r.user) && <span className="ml-2 inline-block align-middle"><SystemAccountBadge /></span>}
          {r.user.display_name && <span className="block break-all text-sm font-normal text-slate-600">{r.user.email}</span>}
        </>
      ),
    },
    { key: "where", header: t("platformAdmin.teachers.columns.where"), cell: (r) => <span className="break-words">{where(r)}</span> },
    {
      key: "status", header: t("platformAdmin.teachers.columns.status"),
      cell: (r) => (r.teacher_status === "none" && !r.disabled) ? dash : (
        <span className="inline-flex flex-wrap justify-end gap-1 sm:justify-start">
          {r.teacher_status !== "none" && <UserStatusBadge kind="teacher" status={r.teacher_status} />}
          {r.disabled && <UserStatusBadge kind="account" status="disabled" />}
        </span>
      ),
    },
    { key: "courses", header: t("platformAdmin.teachers.columns.courses"), align: "right", cell: (r) => r.courses },
    { key: "students", header: t("platformAdmin.teachers.columns.students"), align: "right", cell: (r) => r.students },
    { key: "listed", header: t("platformAdmin.teachers.columns.listed"), align: "right", hideOnMobile: true, cell: (r) => r.listed_courses },
    {
      key: "login", header: t("platformAdmin.teachers.columns.lastLogin"), nowrap: true, hideOnMobile: true,
      cell: (r) => (r.last_login_at ? fmtApiDateTimeShort(r.last_login_at, lang) : <span className="text-slate-500">{t("platformAdmin.users.neverLoggedIn")}</span>),
    },
    { key: "since", header: t("platformAdmin.teachers.columns.since"), nowrap: true, hideOnMobile: true, cell: (r) => (r.since ? fmtApiDate(r.since, lang) : dash) },
  ];
  const filtered = !!(q || kind || status);
  const tabsId = "admin-teachers";
  return (
    <div className={`w-full ${STAFF_WIDTH.list}`}>
      <PageHeader title={t("platformAdmin.teachers.title")} description={t("platformAdmin.teachers.subtitle")} breadcrumbs={crumbs({ label: t("platformAdmin.teachers.title") })} />
      <Tabs id={tabsId} label={t("platformAdmin.teachers.tabsLabel")} value={tab} onChange={(v) => setTab(v as Tab)}
        items={[
          { id: "teachers", label: t("platformAdmin.teachers.tabs.teachers") },
          { id: "requests", label: t("platformAdmin.teachers.tabs.requests"), count: pending ? pending : undefined },
        ]} />
      <TabPanel tabsId={tabsId} value={tab}>
        {tab === "teachers" ? (
          <>
            <Table caption={t("platformAdmin.teachers.title")} density="compact" columns={columns} rows={list.items} rowKey={(r) => r.user.id} {...table}
              search={
                <FilterBar
                  search={{ value: input, onChange: setInput, label: t("lms.common.search"), placeholder: t("platformAdmin.teachers.searchPlaceholder") }}
                  canReset={filtered} onReset={() => { setInput(""); setKind(""); setStatus(""); }}
                >
                  <Select label={t("platformAdmin.teachers.filters.kind")} value={kind} onChange={(e) => setKind(e.target.value as TeacherListKind | "")}
                    options={KINDS.map((k) => ({ value: k, label: t(`platformAdmin.teachers.filters.kinds.${k || "any"}`) }))} />
                  <Select label={t("platformAdmin.teachers.filters.status")} value={status} onChange={(e) => setStatus(e.target.value as TeacherListStatus | "")}
                    options={STATUSES.map((s) => ({ value: s, label: s ? t(`platformAdmin.teacherStatus.${s}`) : t("platformAdmin.teachers.filters.anyStatus") }))} />
                </FilterBar>
              }
              empty={<EmptyState variant="plain" title={t(filtered ? "platformAdmin.teachers.emptySearch" : "platformAdmin.teachers.empty")} />} />
            <MoreError list={list} />
          </>
        ) : (
          <TeacherRequestsPanel filter={requestFilter} onFilterChange={setRequestFilter} onChanged={() => void list.reload()} />
        )}
      </TabPanel>
    </div>
  );
}

export default function AdminTeachersPage() {
  return (
    <Suspense fallback={null}>
      <AdminTeachers />
    </Suspense>
  );
}
