"use client";

// Phase 9 S4: Course → People → Applications (S3's `applications` slot; PHASE_9_DESIGN 4.7, 8.1, 8.4). A status filter
// (pending first), search on the applicant's name or email (never on answers), keyset pagination, and a row opens
// `ApplicationPanel`. No export: answers never leave the panel.
import React, { useCallback, useState } from "react";
import { Inbox } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listApplications } from "@/lib/lms/applications";
import type { ApplicationOut, ApplicationStatus, Lang } from "@/lib/lms/types";
import { Button, EmptyState, SearchInput, Select, Table, type TableColumn } from "@/components/ui";
import { useCursorList, useDebounced } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { ApplicationStatusBadge } from "@/components/lms/catalog/ApplicationStatus";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { ApplicationPanel, applicantName } from "./ApplicationPanel";

const STATUSES: ApplicationStatus[] = ["pending", "approved", "rejected", "withdrawn"];

export function ApplicationsInbox({
  courseId, canDecide, defaultLanguage, courseOpen, onChanged,
}: {
  courseId: string;
  canDecide: boolean;
  defaultLanguage: Lang;
  courseOpen: boolean;
  /** After a decision (the roster may have a new student). */
  onChanged?: () => void;
}) {
  const { lang, t } = useTranslation();
  const [status, setStatus] = useState<"" | ApplicationStatus>("pending");
  const [q, setQ] = useState("");
  const query = useDebounced(q);
  const [openId, setOpenId] = useState<string | null>(null);

  const fetchPage = useCallback(
    (cursor: string | null) => listApplications(courseId, { status, q: query, cursor }),
    [courseId, status, query],
  );
  const list = useCursorList(fetchPage);
  const tableState = useTableState(list);

  const onDecided = (a: ApplicationOut) => {
    // Keep the row in place with its new status until the filter is changed (the panel stays readable).
    list.setItems((rows) => rows.map((r) => (r.id === a.id ? a : r)));
    onChanged?.();
  };

  const columns: TableColumn<ApplicationOut>[] = [
    { key: "applicant", header: t("applications.inbox.applicant"), primary: true, className: "sm:min-w-[12rem]",
      cell: (a) => (
        <span className="block min-w-0">
          <span className="block font-medium text-slate-900 [overflow-wrap:anywhere]">{applicantName(a)}</span>
          {a.applicant.display_name && <span className="block text-sm text-slate-600 [overflow-wrap:anywhere]">{a.applicant.email}</span>}
        </span>
      ) },
    { key: "status", header: t("applications.inbox.status"), cell: (a) => <ApplicationStatusBadge status={a.status} /> },
    { key: "submitted", header: t("applications.inbox.submitted"), nowrap: true, cell: (a) => fmtShortDateTime(a.submitted_at, lang) },
    { key: "actions", header: "", actions: true, align: "right",
      cell: (a) => (
        <Button variant="secondary" size="sm" onClick={() => setOpenId(a.id)}>
          {a.status === "pending" && canDecide ? t("applications.inbox.review") : t("applications.inbox.view")}
          <span className="sr-only">: {applicantName(a)}</span>
        </Button>
      ) },
  ];

  const filtered = !!status || !!query;

  return (
    <section aria-labelledby="applications-title">
      <h2 id="applications-title" className="sr-only">{t("applications.inbox.title")}</h2>
      <Table
        caption={t("applications.inbox.title")}
        columns={columns}
        rows={list.items}
        rowKey={(a) => a.id}
        {...tableState}
        search={
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <Select id="applications-status" label={t("applications.inbox.status")} value={status} containerClassName="sm:max-w-xs"
              onChange={(e) => setStatus(e.target.value as "" | ApplicationStatus)}
              options={[{ value: "", label: t("applications.inbox.all") }, ...STATUSES.map((s) => ({ value: s, label: t(`applications.status.${s}`) }))]} />
            <SearchInput id="applications-q" value={q} onChange={setQ} label={t("applications.inbox.search")} maxLength={80}
              containerClassName="min-w-0 sm:flex-1" />
          </div>
        }
        empty={
          <EmptyState icon={<Inbox />}
            title={filtered ? t("applications.inbox.emptyFilter") : t("applications.inbox.empty")}
            description={filtered ? undefined : t("applications.inbox.emptyHint")}
            action={status === "pending" && !query ? (
              <Button variant="secondary" onClick={() => setStatus("")}>{t("applications.inbox.showAll")}</Button>
            ) : undefined} />
        }
      />
      <MoreError list={list} />
      <ApplicationPanel courseId={courseId} applicationId={openId} open={!!openId} onClose={() => setOpenId(null)}
        canDecide={canDecide} defaultLanguage={defaultLanguage} courseOpen={courseOpen} onDecided={onDecided} />
    </section>
  );
}
