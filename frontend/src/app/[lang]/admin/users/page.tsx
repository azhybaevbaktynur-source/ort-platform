"use client";

import React, { useCallback, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { listUsers } from "@/lib/lms/admin";
import type { AdminUserOut, TeacherStatus } from "@/lib/lms/types";
import { isSystemAccount } from "@/lib/lms/organizations";
import { fmtApiDate } from "@/lib/format";
import { Checkbox, EmptyState, FilterBar, PageHeader, Select, Table, type TableColumn } from "@/components/ui";
import { UserStatusBadge } from "@/components/lms/admin/UserStatusBadge";
import { SystemAccountBadge } from "@/components/lms/org/OrgUi";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useCursorList, useDebounced } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";

const STATUSES: (TeacherStatus | "")[] = ["", "none", "pending", "approved", "revoked"];

/**
 * Users (admin M2): a `Table` that becomes cards on phones (name + email, teacher status, account badges,
 * created). Block / unblock moved to the user's page so the list stays calm.
 */
export default function AdminUsersPage() {
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const [input, setInput] = useState("");
  const q = useDebounced(input);
  const [status, setStatus] = useState<TeacherStatus | "">("");
  const [disabledOnly, setDisabledOnly] = useState(false);
  const fetchPage = useCallback(
    (cursor: string | null) => listUsers({ q, teacher_status: status, disabled: disabledOnly ? true : undefined, cursor }),
    [q, status, disabledOnly],
  );
  const list = useCursorList(fetchPage);
  const state = useTableState(list);

  const columns: TableColumn<AdminUserOut>[] = [
    {
      key: "user", header: t("platformAdmin.users.user"), primary: true,
      cell: (u) => (
        <>
          <Link href={`/${lang}/admin/users/${u.id}`} className="break-words font-semibold text-brand-700 hover:underline">{u.display_name || u.email}</Link>
          <span className="block break-all text-sm font-normal text-slate-600">{u.email}</span>
        </>
      ),
    },
    { key: "teacher", header: t("platformAdmin.users.teacherStatus"), cell: (u) => <UserStatusBadge kind="teacher" status={u.teacher_status} /> },
    {
      key: "account", header: t("platformAdmin.users.account"),
      cell: (u) => {
        const system = isSystemAccount(u); // Phase 6 S4 (admin M5)
        if (!system && !u.is_platform_admin && !u.disabled_at) return <span className="text-slate-500">—</span>;
        return (
          <span className="inline-flex flex-wrap justify-end gap-1 sm:justify-start">
            {system && <SystemAccountBadge />}
            {u.is_platform_admin && <UserStatusBadge kind="account" status="admin" />}
            {u.disabled_at && <UserStatusBadge kind="account" status="disabled" />}
          </span>
        );
      },
    },
    { key: "created", header: t("platformAdmin.users.created"), nowrap: true, cell: (u) => fmtApiDate(u.created_at, lang) },
  ];
  const filtered = !!(q || status || disabledOnly);
  return (
    <div>
      <PageHeader title={t("platformAdmin.users.title")} breadcrumbs={crumbs({ label: t("platformAdmin.users.title") })} />
      <Table
        caption={t("platformAdmin.users.title")}
        columns={columns}
        rows={list.items}
        rowKey={(u) => u.id}
        {...state}
        search={
          <FilterBar
            search={{ value: input, onChange: setInput, label: t("lms.common.search"), placeholder: t("platformAdmin.users.searchPlaceholder") }}
            canReset={filtered} onReset={() => { setInput(""); setStatus(""); setDisabledOnly(false); }}
          >
            <Select label={t("platformAdmin.users.teacherStatus")} value={status} onChange={(e) => setStatus(e.target.value as TeacherStatus | "")}
              options={STATUSES.map((s) => ({ value: s, label: s ? t(`platformAdmin.teacherStatus.${s}`) : t("platformAdmin.users.anyStatus") }))} />
            <Checkbox label={t("platformAdmin.users.disabledOnly")} checked={disabledOnly} onChange={(e) => setDisabledOnly(e.target.checked)} />
          </FilterBar>
        }
        empty={<EmptyState title={t("platformAdmin.users.empty")} />}
      />
      <MoreError list={list} />
    </div>
  );
}
