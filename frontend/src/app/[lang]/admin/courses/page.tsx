"use client";

import React, { useCallback, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { listAdminCourses } from "@/lib/lms/admin";
import type { AdminCourseOut } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import { isSystemAccount } from "@/lib/lms/organizations";
import { Badge, Checkbox, EmptyState, FilterBar, PageHeader, Table, type TableColumn } from "@/components/ui";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useCursorList, useDebounced } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { CourseStatusBadge, SystemAccountBadge } from "@/components/lms/org/OrgUi";

export default function AdminCoursesPage() {
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const [input, setInput] = useState("");
  const q = useDebounced(input);
  const [deleted, setDeleted] = useState(false);
  const fetchPage = useCallback((cursor: string | null) => listAdminCourses({ q, deleted: deleted ? true : undefined, cursor }), [q, deleted]);
  const list = useCursorList(fetchPage);
  const state = useTableState(list);

  const columns: TableColumn<AdminCourseOut>[] = [
    {
      key: "course", header: t("platformAdmin.courses.course"), primary: true,
      cell: (c) => <Link href={`/${lang}/admin/courses/${c.id}`} className="break-words font-semibold text-brand-700 hover:underline">{pickLocalized(c.title, lang, "en") || c.id}</Link>,
    },
    {
      key: "owner", header: t("platformAdmin.courses.owner"),
      cell: (c) => (
        <span className="inline-flex flex-wrap items-center justify-end gap-1.5 sm:justify-start">
          <span className="break-words">{c.owner.display_name || c.owner.email}</span>
          {isSystemAccount(c.owner) && <SystemAccountBadge />}
        </span>
      ),
    },
    { key: "status", header: t("platformAdmin.courses.status"), cell: (c) => <CourseStatusBadge status={c.status} /> },
    { key: "students", header: t("platformAdmin.courses.students"), align: "right", cell: (c) => c.active_student_count },
    {
      key: "flags", header: t("platformAdmin.courses.flags"),
      cell: (c) => (!c.deleted_at && !c.unlisted_by_admin_at) ? <span className="text-slate-500">—</span> : (
        <span className="inline-flex flex-wrap justify-end gap-1 sm:justify-start">
          {c.deleted_at && <Badge tone="danger">{t("platformAdmin.courses.deleted")}</Badge>}
          {c.unlisted_by_admin_at && <Badge tone="warning">{t("platformAdmin.courses.unlisted")}</Badge>}
        </span>
      ),
    },
  ];
  const filtered = !!(q || deleted);
  return (
    <div>
      <PageHeader title={t("platformAdmin.courses.title")} breadcrumbs={crumbs({ label: t("platformAdmin.courses.title") })} />
      <Table
        caption={t("platformAdmin.courses.title")}
        columns={columns}
        rows={list.items}
        rowKey={(c) => c.id}
        {...state}
        search={
          <FilterBar
            search={{ value: input, onChange: setInput, label: t("lms.common.search"), placeholder: t("platformAdmin.courses.searchPlaceholder") }}
            canReset={filtered} onReset={() => { setInput(""); setDeleted(false); }}
          >
            <Checkbox label={t("platformAdmin.courses.deletedOnly")} checked={deleted} onChange={(e) => setDeleted(e.target.checked)} />
          </FilterBar>
        }
        empty={<EmptyState title={t("platformAdmin.courses.empty")} />}
      />
      <MoreError list={list} />
    </div>
  );
}
