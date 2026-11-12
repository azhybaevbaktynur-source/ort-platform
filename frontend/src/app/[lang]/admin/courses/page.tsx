"use client";

import React, { Suspense, useCallback, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { listAdminCourses } from "@/lib/lms/admin";
import type { AdminCourseOut } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import { isSystemAccount } from "@/lib/lms/organizations";
import { Badge, Checkbox, EmptyState, FilterBar, PageHeader, STAFF_WIDTH, Table, type TableColumn } from "@/components/ui";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useCursorList, useDebounced } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { CourseStatusBadge, SystemAccountBadge } from "@/components/lms/org/OrgUi";
import { LISTING_TONE } from "@/lib/lms/listing";

export default function AdminCoursesPage() {
  return (
    <Suspense fallback={null}>
      <AdminCourses />
    </Suspense>
  );
}

function AdminCourses() {
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const [input, setInput] = useState("");
  const q = useDebounced(input);
  const [deleted, setDeleted] = useState(false);
  // step 3b S3: the person page's «Преподавание» card links here with `?owner_id=` (one teacher's courses)
  const ownerId = useSearchParams().get("owner_id") || undefined;
  const fetchPage = useCallback((cursor: string | null) => listAdminCourses({ q, deleted: deleted ? true : undefined, owner_id: ownerId, cursor }), [q, deleted, ownerId]);
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
      // step 3b S2: the catalog listing state (anything but `off`) next to the trash flag
      cell: (c) => {
        const listing = c.listing && c.listing.state !== "off" ? c.listing.state : null;
        return (!c.deleted_at && !listing) ? <span className="text-slate-500">—</span> : (
          <span className="inline-flex flex-wrap justify-end gap-1 sm:justify-start">
            {c.deleted_at && <Badge tone="danger">{t("platformAdmin.courses.deleted")}</Badge>}
            {listing && <Badge tone={LISTING_TONE[listing]}>{t(`catalog.listing.states.${listing}`)}</Badge>}
          </span>
        );
      },
    },
  ];
  const filtered = !!(q || deleted);
  return (
    <div className={`w-full ${STAFF_WIDTH.list}`}>
      <PageHeader title={t("platformAdmin.courses.title")} description={t("platformAdmin.courses.subtitle")} breadcrumbs={crumbs({ label: t("platformAdmin.courses.title") })} />
      {ownerId && (
        <p className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-700">
          {t("platformAdmin.courses.ownerFilter")}
          <Link href={`/${lang}/admin/users/${encodeURIComponent(ownerId)}`} className="inline-flex min-h-11 items-center font-medium text-brand-700 hover:underline sm:min-h-0">{t("platformAdmin.courses.ownerFilterPerson")}</Link>
          <Link href={`/${lang}/admin/courses`} className="inline-flex min-h-11 items-center font-medium text-brand-700 hover:underline sm:min-h-0">{t("platformAdmin.courses.ownerFilterReset")}</Link>
        </p>
      )}
      <Table
        caption={t("platformAdmin.courses.title")}
        density="compact"
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
