"use client";

// Step 3b S3 (CATALOG_AND_TEACHERS_DESIGN 3.2, owner D9): the teacher requests queue, moved from the old
// /admin/teacher-requests page into the «Заявки» tab of Admin → Преподаватели. The status filter is a select here (the
// page's own tabs are Преподаватели · Заявки).
import React, { useCallback, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { approveTeacherRequest, getUser, listTeacherRequests, rejectTeacherRequest, setTeacherStatus } from "@/lib/lms/admin";
import type { TeacherRequestAdminOut, TeacherRequestStatus } from "@/lib/lms/types";
import { fmtApiDateTimeShort } from "@/lib/format";
import { Badge, Button, DescriptionList, EmptyState, FilterBar, OverflowMenu, ReasonDialog, Select, Sheet, Table, toast, type TableColumn } from "@/components/ui";
import { UserStatusBadge } from "@/components/lms/admin/UserStatusBadge";
import { useAdminSummary } from "@/components/lms/admin/AdminShell";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { OrgError } from "@/components/lms/org/OrgUi";

export type RequestFilter = TeacherRequestStatus | "all";
// Phase 6 S4 (admin M7): the teacher status a request status implies; a badge shows only when they differ.
const IMPLIED_TEACHER_STATUS: Record<string, string> = { pending: "pending", approved: "approved", rejected: "none", cancelled: "none" };
export const REQUEST_FILTERS: RequestFilter[] = ["pending", "approved", "rejected", "all"];
const REQUEST_TONE: Record<string, "warning" | "success" | "danger" | "neutral"> = { pending: "warning", approved: "success", rejected: "danger", cancelled: "neutral" };

export function TeacherRequestsPanel({ filter, onFilterChange, onChanged }: {
  filter: RequestFilter;
  onFilterChange: (f: RequestFilter) => void;
  /** After an approval, a rejection or a revoke (the Teachers tab reloads). */
  onChanged?: () => void;
}) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { refresh } = useAdminSummary();
  const fetchPage = useCallback((cursor: string | null) => listTeacherRequests(filter, cursor), [filter]);
  const list = useCursorList(fetchPage);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [dialog, setDialog] = useState<{ kind: "reject" | "revoke"; req: TeacherRequestAdminOut } | null>(null);
  const [revokeImpact, setRevokeImpact] = useState<{ students: number; courses: number } | null>(null);
  const [dialogError, setDialogError] = useState<unknown>(null);
  const [details, setDetails] = useState<TeacherRequestAdminOut | null>(null);
  const state = useTableState(list);

  const replace = (u: TeacherRequestAdminOut) => list.setItems((prev) => prev.map((r) => (r.id === u.id ? u : r)));
  const nameOf = (r: TeacherRequestAdminOut) => r.user.display_name || r.user.email;

  const approve = async (r: TeacherRequestAdminOut) => {
    setBusyId(r.id);
    setActionError(null);
    try {
      await approveTeacherRequest(r.id);
      toast.success(t("platformAdmin.toast.approved", { name: nameOf(r) }));
      await list.reload();
      refresh();
      onChanged?.();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusyId(null);
    }
  };

  // Q6 (docs/DISCUSSION_ACCOUNTS.md): a revoke says who it freezes. If the numbers can't load, the general wording still warns.
  const openRevoke = async (req: TeacherRequestAdminOut) => {
    setDialogError(null);
    setBusyId(req.id);
    let impact: { students: number; courses: number } | null = null;
    try {
      impact = (await getUser(req.user.id)).revoke_impact ?? null;
    } catch { /* the dialog falls back to the general wording */ }
    setRevokeImpact(impact);
    setBusyId(null);
    setDialog({ kind: "revoke", req });
  };

  const confirm = async (reason: string) => {
    if (!dialog) return;
    setBusyId(dialog.req.id);
    setDialogError(null);
    try {
      if (dialog.kind === "reject") {
        await rejectTeacherRequest(dialog.req.id, reason);
        toast.success(t("platformAdmin.toast.rejected", { name: nameOf(dialog.req) }));
        await list.reload();
        refresh();
      } else {
        await setTeacherStatus(dialog.req.user.id, "revoked", reason || undefined);
        toast.success(t("platformAdmin.toast.revoked", { name: nameOf(dialog.req) }));
        replace({ ...dialog.req, user_teacher_status: "revoked" });
      }
      onChanged?.();
      setDialog(null);
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusyId(null);
    }
  };

  const columns: TableColumn<TeacherRequestAdminOut>[] = [
    {
      key: "applicant", header: t("platformAdmin.requests.applicant"), primary: true,
      cell: (r) => (
        <>
          <button type="button" onClick={() => setDetails(r)} className="break-words text-left font-semibold text-brand-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600">{r.applicant_name || nameOf(r)}</button>
          <span className="block break-all text-sm font-normal text-slate-600">{r.user.email}</span>
        </>
      ),
    },
    { key: "school", header: t("platformAdmin.requests.school"), cell: (r) => r.school || <span className="text-slate-500">—</span>, hideInCard: (r) => !r.school },
    { key: "subject", header: t("platformAdmin.requests.subject"), cell: (r) => r.subject || <span className="text-slate-500">—</span>, hideInCard: (r) => !r.subject },
    {
      // Phase 6 S4 (admin M7): request status; teacher status only when it differs, prefixed "Now:"
      key: "status", header: t("platformAdmin.requests.status"),
      cell: (r) => (
        <span className="inline-flex flex-wrap items-center justify-end gap-1.5 sm:justify-start">
          <Badge tone={REQUEST_TONE[r.status] ?? "neutral"}>{t(`teacherRequest.requestStatus.${r.status}`)}</Badge>
          {r.user_teacher_status !== IMPLIED_TEACHER_STATUS[r.status] && (
            <span className="inline-flex items-center gap-1 text-sm text-slate-600">{t("organizations.adminUser.nowPrefix")} <UserStatusBadge kind="teacher" status={r.user_teacher_status} /></span>
          )}
        </span>
      ),
    },
    { key: "submitted", header: t("platformAdmin.requests.submitted"), nowrap: true, cell: (r) => fmtApiDateTimeShort(r.created_at, lang) },
    {
      key: "actions", header: <span className="sr-only">{t("platformAdmin.requests.actions")}</span>, label: t("platformAdmin.requests.actions"), actions: true, align: "right",
      cell: (r) => {
        const danger = [
          ...(r.status === "pending" ? [{ id: "reject", label: t("platformAdmin.requests.reject"), danger: true }] : []),
          ...(r.user_teacher_status === "approved" ? [{ id: "revoke", label: t("platformAdmin.requests.revoke"), danger: true }] : []),
        ];
        return (
          <span className="inline-flex items-center justify-end gap-2">
            {r.status === "pending" && (
              <Button size="sm" loading={busyId === r.id && !dialog} disabled={busyId === r.id} onClick={() => void approve(r)}>{t("platformAdmin.requests.approve")}</Button>
            )}
            <OverflowMenu
              groups={[{ id: "r", items: [{ id: "details", label: t("platformAdmin.requests.details") }, { id: "user", label: t("platformAdmin.requests.openUser") }, ...danger] }]}
              onSelect={(id) => {
                if (id === "details") setDetails(r);
                else if (id === "user") router.push(`/${lang}/admin/users/${r.user.id}`);
                else if (id === "reject") { setDialogError(null); setDialog({ kind: "reject", req: r }); }
                else if (id === "revoke") void openRevoke(r);
              }} />
          </span>
        );
      },
    },
  ];

  const d = details;
  const detailItems = d ? [
    { key: "email", term: t("platformAdmin.requests.email"), description: <span className="break-all">{d.user.email}</span> },
    { key: "school", term: t("platformAdmin.requests.school"), description: d.school },
    { key: "subject", term: t("platformAdmin.requests.subject"), description: d.subject },
    { key: "phone", term: t("platformAdmin.requests.phone"), description: d.phone && (
      <a href={`tel:${d.phone.replace(/[^0-9+]/g, "")}`} className="inline-flex min-h-11 items-center font-medium text-brand-700 hover:underline sm:min-h-0">{d.phone}</a>
    ) },
    { key: "teachesAt", term: t("platformAdmin.requests.teachesAt"), description: (d.teaches_at?.length ?? 0) > 0 ? d.teaches_at.join(", ") : null },
    { key: "message", term: t("platformAdmin.requests.message"), description: d.message ? <span className="whitespace-pre-wrap">{d.message}</span> : null },
    { key: "reason", term: t("teacherRequest.reason"), description: d.reason && <span className="break-words">{d.reason}</span> },
    { key: "decided", term: t("platformAdmin.requests.decided"), description: d.decided_by && d.decided_at
      ? t("platformAdmin.requests.decidedBy", { name: d.decided_by.display_name || d.decided_by.email, date: fmtApiDateTimeShort(d.decided_at, lang) }) : null },
  ].filter((it) => it.description) : [];
  return (
    <>
      <p className="mb-4 text-sm text-slate-600">{t("platformAdmin.requests.subtitle")}</p>
      {actionError ? <OrgError error={actionError} className="mb-4" /> : null}
      <Table caption={t("platformAdmin.requests.title")} density="compact" columns={columns} rows={list.items} rowKey={(r) => r.id} {...state}
        search={
          <FilterBar>
            <Select label={t("platformAdmin.requests.filter")} value={filter} onChange={(e) => onFilterChange(e.target.value as RequestFilter)}
              options={REQUEST_FILTERS.map((f) => ({ value: f, label: t(`platformAdmin.requests.filters.${f}`) }))} />
          </FilterBar>
        }
        empty={<EmptyState variant="plain" title={t("platformAdmin.requests.empty")} />} />
      <MoreError list={list} />
      <Sheet open={!!d} onClose={() => setDetails(null)} title={d ? (d.applicant_name || nameOf(d)) : ""}>
        {d && (
          <div className="space-y-4">
            {detailItems.length > 0 ? <DescriptionList items={detailItems} /> : <p className="text-sm text-slate-600">{t("platformAdmin.requests.noMessage")}</p>}
            <Link href={`/${lang}/admin/users/${d.user.id}`} className="inline-flex min-h-11 items-center text-sm font-medium text-brand-700 hover:underline sm:min-h-0">{t("platformAdmin.requests.openUser")}</Link>
          </div>
        )}
      </Sheet>
      <ReasonDialog
        open={!!dialog}
        title={dialog?.kind === "reject" ? t("platformAdmin.requests.rejectTitle") : t("platformAdmin.requests.revokeTitle")}
        object={dialog ? (dialog.req.user.display_name ? `${dialog.req.user.display_name} · ${dialog.req.user.email}` : dialog.req.user.email) : undefined}
        effect={dialog?.kind === "reject" ? t("platformAdmin.requests.rejectBody")
          : revokeImpact ? t("platformAdmin.users.revokeImpact", revokeImpact) : t("platformAdmin.requests.revokeBody")}
        confirmLabel={dialog?.kind === "reject" ? t("platformAdmin.requests.reject") : t("platformAdmin.requests.revoke")}
        tone="danger" busy={!!busyId}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(r) => void confirm(r)} onCancel={() => setDialog(null)}
      />
    </>
  );
}
