"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { AuditEntryOut } from "@/lib/lms/types";
import { fmtApiDateTime } from "@/lib/format";
import { Table, type PaginationProps, type TableColumn } from "@/components/ui";
import { focusRing } from "@/components/ui";

export function useAuditActionLabel() {
  const { t } = useTranslation();
  return (action: string) => {
    const key = `platformAdmin.auditActions.${action.replace(/\./g, "_")}`;
    const label = t(key);
    return label === key ? action : label;
  };
}

/**
 * Audit entries as a `Table` (Phase 6b S5b): stacked cards on phones (action, when, who, reason) with the
 * object and the raw details behind a "Details" disclosure. M3 (labels instead of ids) is Phase 7.
 */
export function AuditTable({ entries, loading, error, empty, pagination, countText, caption }: {
  entries: AuditEntryOut[];
  loading?: boolean;
  error?: React.ReactNode;
  empty?: React.ReactNode;
  pagination?: PaginationProps;
  countText?: string;
  caption?: string;
}) {
  const { t, lang } = useTranslation();
  const label = useAuditActionLabel();
  const details = (e: AuditEntryOut) => (e.details && Object.keys(e.details).length ? JSON.stringify(e.details) : "—");
  const columns: TableColumn<AuditEntryOut>[] = [
    { key: "action", header: t("platformAdmin.audit.action"), primary: true, cell: (e) => label(e.action) },
    { key: "when", header: t("platformAdmin.audit.when"), nowrap: true, cell: (e) => fmtApiDateTime(e.created_at, lang) },
    { key: "actor", header: t("platformAdmin.audit.actor"), cell: (e) => e.actor.display_name || e.actor.email },
    {
      key: "target", header: t("platformAdmin.audit.target"), hideOnMobile: true,
      cell: (e) => <><span className="text-slate-600">{e.target_type}</span> <code className="break-all text-xs">{e.target_id}</code></>,
    },
    { key: "reason", header: t("platformAdmin.audit.reason"), cell: (e) => e.reason || "—" },
    {
      key: "details", header: t("platformAdmin.audit.details"), hideOnMobile: true,
      cell: (e) => <code className="break-all text-xs text-slate-700">{details(e)}</code>,
    },
    {
      key: "more", header: "", actions: true, className: "sm:hidden", headerClassName: "sm:hidden",
      cell: (e) => (
        <details className="w-full whitespace-normal sm:hidden">
          <summary className={`inline-flex min-h-11 cursor-pointer items-center rounded-lg text-sm font-semibold text-brand-700 ${focusRing}`}>
            {t("platformAdmin.audit.details")}
          </summary>
          <p className="break-all text-xs"><span className="text-slate-600">{e.target_type}</span> <code>{e.target_id}</code></p>
          <code className="mt-1 block break-all text-xs text-slate-700">{details(e)}</code>
        </details>
      ),
    },
  ];
  return (
    <Table
      caption={caption ?? t("platformAdmin.audit.title")}
      columns={columns}
      rows={entries}
      rowKey={(e) => e.id}
      loading={loading}
      error={error}
      empty={empty}
      pagination={pagination}
      countText={countText}
    />
  );
}
