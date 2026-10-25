"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { OrgCourseOut } from "@/lib/lms/organizations";
import { templateTitle } from "@/lib/lms/templates";
import { Table, type PaginationProps, type TableColumn } from "@/components/ui";
import { CourseStatusBadge } from "./OrgUi";

/** Courses table (title, owner, template, status, students) for the org admin and platform admin organization pages. */
export function OrgCourseList({ courses, hrefFor, loading, error, empty, pagination, countText, search }: {
  courses: OrgCourseOut[];
  hrefFor: (c: OrgCourseOut) => string;
  loading?: boolean;
  error?: React.ReactNode;
  empty?: React.ReactNode;
  pagination?: PaginationProps;
  countText?: string;
  search?: React.ReactNode;
}) {
  const { lang, t } = useTranslation();
  const columns: TableColumn<OrgCourseOut>[] = [
    {
      key: "title", header: t("platformAdmin.courses.course"), primary: true,
      cell: (c) => <Link href={hrefFor(c)} className="break-words font-semibold text-brand-700 hover:underline">{pickLocalized(c.title, lang) || c.id}</Link>,
    },
    { key: "owner", header: t("organizations.courses.owner"), cell: (c) => c.owner.display_name || c.owner.email },
    { key: "template", header: t("templates.field"), cell: (c) => (c.template_key ? templateTitle(t, c.template_key) : t("templates.general")) },
    { key: "status", header: t("platformAdmin.courses.status"), cell: (c) => <CourseStatusBadge status={c.status} /> },
    { key: "students", header: t("organizations.counts.students"), align: "right", cell: (c) => c.active_student_count },
  ];
  return (
    <Table caption={t("organizations.courses.title")} columns={columns} rows={courses} rowKey={(c) => c.id}
      loading={loading} error={error} empty={empty} pagination={pagination} countText={countText} search={search} />
  );
}
