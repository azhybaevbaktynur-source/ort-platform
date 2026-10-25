"use client";

import React, { useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { AuditEntryOut } from "@/lib/lms/types";
import { fmtApiDateTimeShort } from "@/lib/format";
import { Button, Dialog, Table, type PaginationProps, type TableColumn } from "@/components/ui";
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
  const hasDetails = (e: AuditEntryOut) => !!e.details && Object.keys(e.details).length > 0;
  const details = (e: AuditEntryOut) => (hasDetails(e) ? JSON.stringify(e.details) : "—");
  const prettyDetails = (e: AuditEntryOut) => JSON.stringify(e.details, null, 2);
  const [open, setOpen] = useState<AuditEntryOut | null>(null);
  const columns: TableColumn<AuditEntryOut>[] = [
    { key: "action", header: t("platformAdmin.audit.action"), primary: true, cell: (e) => label(e.action) },
    { key: "when", header: t("platformAdmin.audit.when"), nowrap: true, cell: (e) => fmtApiDateTimeShort(e.created_at, lang) },
    { key: "actor", header: t("platformAdmin.audit.actor"), cell: (e) => e.actor.display_name || e.actor.email },
    {
      key: "target", header: t("platformAdmin.audit.target"), hideOnMobile: true,
      cell: (e) => <><span className="text-slate-600">{e.target_type}</span> <code className="break-all text-xs">{e.target_id}</code></>,
    },
    { key: "reason", header: t("platformAdmin.audit.reason"), cell: (e) => e.reason || "—" },
    {
      // Phase 6b S11b (UX 7): the raw details open in a dialog from a "Details" button instead of a JSON blob in the row.
      key: "details", header: t("platformAdmin.audit.details"), hideOnMobile: true, nowrap: true,
      cell: (e) => hasDetails(e) ? (
        <Button variant="link" size="sm" aria-haspopup="dialog" onClick={() => setOpen(e)}>{t("platformAdmin.audit.details")}</Button>
      ) : <span className="text-slate-500">—</span>,
    },
    {
      key: "more", header: "", actions: true, className: "sm:hidden", headerClassName: "sm:hidden",
      cell: (e) => (
        <details className="w-full whitespace-normal sm:hidden">
          <summary className={`inline-flex min-h-11 cursor-pointer items-center rounded-lg text-sm font-semibold text-brand-700 ${focusRing}`}>
            {t("platformAdmin.audit.details")}
          </summary>
          <p className="break-all text-xs"><span className="text-slate-600">{e.target_type}</span> <code>{e.target_id}</code></p>
          {hasDetails(e)
            ? <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-slate-50 p-2 text-xs text-slate-700">{prettyDetails(e)}</pre>
            : <p className="mt-1 text-xs text-slate-500">{details(e)}</p>}
        </details>
      ),
    },
  ];
  return (
    <>
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
    <Dialog open={!!open} onClose={() => setOpen(null)} size="lg"
      title={open ? label(open.action) : ""}
      description={open ? `${fmtApiDateTimeShort(open.created_at, lang)} · ${open.actor.display_name || open.actor.email}` : undefined}
      footer={<Button variant="secondary" onClick={() => setOpen(null)}>{t("ui.close")}</Button>}>
      {open && (
        <>
          <p className="break-all text-sm"><span className="text-slate-600">{t("platformAdmin.audit.target")}:</span> {open.target_type} <code className="text-xs">{open.target_id}</code></p>
          <pre className="mt-3 max-h-[60vh] overflow-auto whitespace-pre-wrap break-all rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-800">{prettyDetails(open)}</pre>
        </>
      )}
    </Dialog>
    </>
  );
}
