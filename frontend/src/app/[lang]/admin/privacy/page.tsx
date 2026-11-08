"use client";

import React, { useCallback, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { fmtApiDate } from "@/lib/format";
import { Badge, Button, ConfirmDialog, EmptyState, PageHeader, STAFF_WIDTH, Select, TabPanel, Table, Tabs, toast, type TableColumn } from "@/components/ui";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { REQUEST_TONE } from "@/components/privacy/DataRequests";
import { executeAdminRequest, listAdminRequests, rejectAdminRequest, type AdminRequestOut } from "@/components/privacy/privacyApi";
import { PrivacyError } from "@/components/privacy/privacyErrors";

const FILTERS = ["pending", "all"] as const;
const REJECT_CODES = ["identity_unverified", "legal_obligation", "duplicate"] as const;

/** Data requests, oldest due date first: `Run` erases (delete requests only), `Reject` takes a code, never free text. */
export default function AdminPrivacyPage() {
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("pending");
  const fetchPage = useCallback((cursor: string | null) => listAdminRequests(filter === "all" ? null : filter, cursor), [filter]);
  const list = useCursorList(fetchPage);
  const state = useTableState(list);
  const [dialog, setDialog] = useState<{ kind: "run" | "reject"; row: AdminRequestOut } | null>(null);
  const [code, setCode] = useState<string>(REJECT_CODES[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const open = (kind: "run" | "reject", row: AdminRequestOut) => {
    setError(null);
    setCode(REJECT_CODES[0]);
    setDialog({ kind, row });
  };
  const confirm = async () => {
    if (!dialog) return;
    setBusy(true);
    setError(null);
    try {
      if (dialog.kind === "run") await executeAdminRequest(dialog.row.id);
      else await rejectAdminRequest(dialog.row.id, code);
      toast.success(t(dialog.kind === "run" ? "privacy.admin.ranToast" : "privacy.admin.rejectedToast"));
      setDialog(null);
      await list.reload();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const columns: TableColumn<AdminRequestOut>[] = [
    { key: "person", header: t("privacy.admin.person"), primary: true, cell: (r) => <span className="break-all">{r.user_email ?? r.user_id}</span> },
    { key: "kind", header: t("privacy.admin.kind"), cell: (r) => t(`privacy.requests.kind.${r.kind}`) },
    {
      key: "due", header: t("privacy.admin.due"), nowrap: true,
      cell: (r) => (
        <span className="inline-flex flex-wrap items-center gap-2">
          {fmtApiDate(r.due_at, lang)}
          {r.overdue && <Badge tone="danger">{t("privacy.admin.overdue")}</Badge>}
        </span>
      ),
    },
    { key: "status", header: t("privacy.admin.status"), cell: (r) => <Badge tone={REQUEST_TONE[r.status]}>{t(`privacy.requests.status.${r.status}`)}</Badge> },
    {
      key: "actions", header: t("privacy.admin.actions"), actions: true,
      cell: (r) => r.status === "pending" ? (
        <span className="flex flex-wrap gap-2">
          {r.kind === "delete" && <Button size="sm" variant="dangerOutline" onClick={() => open("run", r)}>{t("privacy.admin.run")}</Button>}
          <Button size="sm" variant="secondary" onClick={() => open("reject", r)}>{t("privacy.admin.reject")}</Button>
        </span>
      ) : null,
    },
  ];

  const tabsId = "privacy-requests";
  return (
    <div className={`w-full ${STAFF_WIDTH.list}`}>
      <PageHeader title={t("privacy.admin.title")} description={t("privacy.admin.subtitle")} breadcrumbs={crumbs({ label: t("privacy.admin.title") })} />
      <Tabs id={tabsId} label={t("privacy.admin.filter")} value={filter} onChange={(v) => setFilter(v as (typeof FILTERS)[number])}
        items={FILTERS.map((f) => ({ id: f, label: t(`privacy.admin.filters.${f}`) }))} />
      <TabPanel tabsId={tabsId} value={filter}>
        <Table caption={t("privacy.admin.title")} density="compact" columns={columns} rows={list.items} rowKey={(r) => r.id} {...state}
          empty={<EmptyState variant="plain" title={t("privacy.admin.empty")} />} />
        <MoreError list={list} />
      </TabPanel>
      <ConfirmDialog open={!!dialog} tone="danger" busy={busy}
        title={t(dialog?.kind === "run" ? "privacy.admin.runTitle" : "privacy.admin.rejectTitle")}
        object={dialog?.row.user_email ?? dialog?.row.user_id}
        effect={t(dialog?.kind === "run" ? "privacy.admin.runEffect" : "privacy.admin.rejectEffect")}
        confirmLabel={t(dialog?.kind === "run" ? "privacy.admin.run" : "privacy.admin.reject")}
        error={error ? <PrivacyError error={error} /> : undefined}
        onConfirm={() => void confirm()} onCancel={() => setDialog(null)}>
        {dialog?.kind === "reject" && (
          <Select label={t("privacy.admin.rejectReason")} value={code} onChange={(e) => setCode(e.target.value)}
            options={REJECT_CODES.map((c) => ({ value: c, label: t(`privacy.admin.rejectCodes.${c}`) }))} />
        )}
      </ConfirmDialog>
    </div>
  );
}
