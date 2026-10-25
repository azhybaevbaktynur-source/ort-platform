"use client";

import React, { useCallback, useState } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listOrgCourses } from "@/lib/lms/organizations";
import { Button, EmptyState, LinkButton, PageHeader, SearchInput } from "@/components/ui";
import { useOrg } from "@/components/lms/org/OrgShell";
import { OrgCourseList } from "@/components/lms/org/OrgCourseList";
import { useCursorList, useDebounced } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";

export default function OrgCoursesPage() {
  const { lang, t } = useTranslation();
  const { org, readOnly, crumbs } = useOrg();
  const [input, setInput] = useState("");
  const q = useDebounced(input);
  const fetchPage = useCallback((cursor: string | null) => listOrgCourses(org.id, { cursor }), [org.id]);
  const list = useCursorList(fetchPage);
  // The courses endpoint has no text filter: search the loaded rows (any title language, owner).
  const needle = q.toLowerCase();
  const shown = needle
    ? list.items.filter((c) => [...Object.values(c.title), c.owner.display_name ?? "", c.owner.email]
      .some((v) => (v ?? "").toLowerCase().includes(needle)))
    : list.items;
  const state = useTableState(list, shown.length);

  const base = `/${lang}/org/${org.id}/courses`;
  const create = (variant: "primary" | "secondary") => readOnly ? (
    <Button variant={variant} disabled leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />}>{t("organizations.courses.create")}</Button>
  ) : (
    <LinkButton variant={variant} href={`${base}/new`} leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />}>{t("organizations.courses.create")}</LinkButton>
  );
  return (
    <div>
      <PageHeader title={t("organizations.courses.title")} breadcrumbs={crumbs({ label: t("organizations.org.nav.courses") })} primaryAction={create("primary")} />
      <OrgCourseList
        courses={shown}
        hrefFor={(c) => `${base}/${c.id}`}
        {...state}
        search={<SearchInput value={input} onChange={setInput} label={t("lms.common.search")} placeholder={t("organizations.courses.searchPlaceholder")} containerClassName="sm:max-w-sm" />}
        empty={
          <EmptyState
            title={q ? t("organizations.courses.emptySearch") : t("organizations.courses.empty")}
            action={!q && !readOnly ? create("secondary") : undefined}
          />
        }
      />
      <MoreError list={list} />
    </div>
  );
}
