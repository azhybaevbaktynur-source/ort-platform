"use client";

import React, { useCallback, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { approveTeacherRequest, listTeacherRequests, rejectTeacherRequest, setTeacherStatus } from "@/lib/lms/admin";
import type { TeacherRequestAdminOut, TeacherRequestStatus } from "@/lib/lms/types";
import { fmtApiDateTimeShort } from "@/lib/format";
import { Badge, Button, Card, EmptyState, LoadingState, PageHeader, Pagination, ReasonDialog, TabPanel, Tabs, toast } from "@/components/ui";
import { UserStatusBadge } from "@/components/lms/admin/UserStatusBadge";
import { useAdminCrumbs, useAdminSummary } from "@/components/lms/admin/AdminShell";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError } from "@/components/lms/admin/ListParts";
import { LoadError, OrgError } from "@/components/lms/org/OrgUi";

type Filter = TeacherRequestStatus | "all";
// Phase 6 S4 (admin M7): the teacher status a request status implies; a badge shows only when they differ.
const IMPLIED_TEACHER_STATUS: Record<string, string> = { pending: "pending", approved: "approved", rejected: "none", cancelled: "none" };
const FILTERS: Filter[] = ["pending", "approved", "rejected", "all"];
const REQUEST_TONE: Record<string, "warning" | "success" | "danger" | "neutral"> = { pending: "warning", approved: "success", rejected: "danger", cancelled: "neutral" };

export default function TeacherRequestsPage() {
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const { refresh } = useAdminSummary();
  const [filter, setFilter] = useState<Filter>("pending");
  const fetchPage = useCallback((cursor: string | null) => listTeacherRequests(filter, cursor), [filter]);
  const list = useCursorList(fetchPage);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [dialog, setDialog] = useState<{ kind: "reject" | "revoke"; req: TeacherRequestAdminOut } | null>(null);
  const [dialogError, setDialogError] = useState<unknown>(null);

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
    } catch (e) {
      setActionError(e);
    } finally {
      setBusyId(null);
    }
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
      setDialog(null);
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusyId(null);
    }
  };

  const tabsId = "teacher-requests";
  return (
    <div>
      <PageHeader title={t("platformAdmin.requests.title")} breadcrumbs={crumbs({ label: t("platformAdmin.requests.title") })} />
      <Tabs id={tabsId} label={t("platformAdmin.requests.filter")} value={filter} onChange={(v) => setFilter(v as Filter)}
        items={FILTERS.map((f) => ({ id: f, label: t(`platformAdmin.requests.filters.${f}`) }))} />
      <TabPanel tabsId={tabsId} value={filter}>
        {actionError ? <OrgError error={actionError} className="mb-4" /> : null}
        {list.items.length > 0 && <p className="mb-3 text-sm font-medium text-slate-700" aria-live="polite">{t("shell.list.shown", { n: list.items.length })}</p>}
        {list.error && list.items.length === 0 ? <LoadError error={list.error} onRetry={() => void list.reload()} />
          : list.loading && list.items.length === 0 ? <LoadingState label={t("lms.common.loading")} />
          : list.items.length === 0 ? <EmptyState title={t("platformAdmin.requests.empty")} />
          : (
            <ul className="space-y-3">
              {list.items.map((r) => (
                <Card as="li" key={r.id}>
                  <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                    <div className="min-w-0">
                      <Link href={`/${lang}/admin/users/${r.user.id}`} className="break-words text-base font-semibold text-brand-700 hover:underline">{nameOf(r)}</Link>
                      <p className="break-all text-sm text-slate-600">{r.user.email}</p>
                    </div>
                    {/* Phase 6 S4 (admin M7): request status; teacher status only when it differs, prefixed "Now:" */}
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={REQUEST_TONE[r.status] ?? "neutral"}>{t(`teacherRequest.requestStatus.${r.status}`)}</Badge>
                      {r.user_teacher_status !== IMPLIED_TEACHER_STATUS[r.status] && (
                        <span className="inline-flex items-center gap-1 text-sm text-slate-600">
                          {t("organizations.adminUser.nowPrefix")} <UserStatusBadge kind="teacher" status={r.user_teacher_status} />
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="mt-1 text-sm text-slate-600">{fmtApiDateTimeShort(r.created_at, lang)}</p>
                  <p className="mt-3 whitespace-pre-wrap break-words text-base leading-6 text-slate-800 sm:text-sm">{r.message || t("platformAdmin.requests.noMessage")}</p>
                  {r.reason && <p className="mt-2 break-words text-sm text-slate-800"><strong>{t("teacherRequest.reason")}:</strong> {r.reason}</p>}
                  {r.decided_by && r.decided_at && (
                    <p className="mt-1 text-sm text-slate-600">{t("platformAdmin.requests.decidedBy", { name: r.decided_by.display_name || r.decided_by.email, date: fmtApiDateTimeShort(r.decided_at, lang) })}</p>
                  )}
                  {(r.status === "pending" || r.user_teacher_status === "approved") && (
                    <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:flex-wrap">
                      {r.user_teacher_status === "approved" && (
                        <Button variant="secondary" disabled={busyId === r.id} onClick={() => { setDialogError(null); setDialog({ kind: "revoke", req: r }); }}>
                          {t("platformAdmin.requests.revoke")}
                        </Button>
                      )}
                      {r.status === "pending" && (
                        <>
                          <Button variant="secondary" disabled={busyId === r.id} onClick={() => { setDialogError(null); setDialog({ kind: "reject", req: r }); }}>
                            {t("platformAdmin.requests.reject")}
                          </Button>
                          <Button loading={busyId === r.id && !dialog} disabled={busyId === r.id} onClick={() => void approve(r)} className="sm:order-first">
                            {t("platformAdmin.requests.approve")}
                          </Button>
                        </>
                      )}
                    </div>
                  )}
                </Card>
              ))}
            </ul>
          )}
        <Pagination nextCursor={list.cursor} onLoadMore={list.loadMore} loading={list.loading && list.items.length > 0} />
        <MoreError list={list} />
      </TabPanel>
      <ReasonDialog
        open={!!dialog}
        title={dialog?.kind === "reject" ? t("platformAdmin.requests.rejectTitle") : t("platformAdmin.requests.revokeTitle")}
        object={dialog ? (dialog.req.user.display_name ? `${dialog.req.user.display_name} · ${dialog.req.user.email}` : dialog.req.user.email) : undefined}
        effect={dialog?.kind === "reject" ? t("platformAdmin.requests.rejectBody") : t("platformAdmin.requests.revokeBody")}
        confirmLabel={dialog?.kind === "reject" ? t("platformAdmin.requests.reject") : t("platformAdmin.requests.revoke")}
        tone="danger" optional={dialog?.kind === "revoke"} busy={!!busyId}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(r) => void confirm(r)} onCancel={() => setDialog(null)}
      />
    </div>
  );
}
