"use client";

import React, { useCallback, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { approveTeacherRequest, getUser, listTeacherRequests, rejectTeacherRequest, setTeacherStatus } from "@/lib/lms/admin";
import type { TeacherRequestAdminOut, TeacherRequestStatus } from "@/lib/lms/types";
import { fmtApiDateTimeShort } from "@/lib/format";
import { Badge, Button, Card, DescriptionList, EmptyState, LoadingState, PageHeader, Pagination, ReasonDialog, TabPanel, Tabs, toast } from "@/components/ui";
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

/** What the applicant sent. A request from before the form has only its optional message. */
function RequestFields({ request: r }: { request: TeacherRequestAdminOut }) {
  const { t } = useTranslation();
  const hasForm = !!(r.school || r.subject || r.phone);
  if (!hasForm && !r.message) return <p className="mt-3 text-base leading-6 text-slate-600 sm:text-sm">{t("platformAdmin.requests.noMessage")}</p>;
  const items = [
    { key: "school", term: t("platformAdmin.requests.school"), description: r.school },
    { key: "subject", term: t("platformAdmin.requests.subject"), description: r.subject },
    { key: "phone", term: t("platformAdmin.requests.phone"), description: r.phone && (
      <a href={`tel:${r.phone.replace(/[^0-9+]/g, "")}`} className="inline-flex min-h-11 items-center font-medium text-brand-700 hover:underline sm:min-h-0">{r.phone}</a>
    ) },
    { key: "teachesAt", term: t("platformAdmin.requests.teachesAt"), description: (r.teaches_at?.length ?? 0) > 0 ? r.teaches_at.join(", ") : null },
  ].filter((item) => item.description);
  return (
    <div className="mt-3 space-y-3 border-t border-slate-100 pt-3">
      {items.length > 0 && <DescriptionList twoColumns items={items} />}
      {r.message && <DescriptionList items={[{ key: "message", term: t("platformAdmin.requests.message"), description: <span className="whitespace-pre-wrap">{r.message}</span> }]} />}
    </div>
  );
}

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
  const [revokeImpact, setRevokeImpact] = useState<{ students: number; courses: number } | null>(null);
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
                      <Link href={`/${lang}/admin/users/${r.user.id}`} className="inline-flex min-h-11 items-center break-words text-base font-semibold text-brand-700 hover:underline sm:min-h-0">{r.applicant_name || nameOf(r)}</Link>
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
                  <RequestFields request={r} />
                  {r.reason && <p className="mt-2 break-words text-sm text-slate-800"><strong>{t("teacherRequest.reason")}:</strong> {r.reason}</p>}
                  {r.decided_by && r.decided_at && (
                    <p className="mt-1 text-sm text-slate-600">{t("platformAdmin.requests.decidedBy", { name: r.decided_by.display_name || r.decided_by.email, date: fmtApiDateTimeShort(r.decided_at, lang) })}</p>
                  )}
                  {(r.status === "pending" || r.user_teacher_status === "approved") && (
                    <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:flex-wrap">
                      {r.user_teacher_status === "approved" && (
                        <Button variant="secondary" disabled={busyId === r.id} onClick={() => void openRevoke(r)}>
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
        effect={dialog?.kind === "reject" ? t("platformAdmin.requests.rejectBody")
          : revokeImpact ? t("platformAdmin.users.revokeImpact", revokeImpact) : t("platformAdmin.requests.revokeBody")}
        confirmLabel={dialog?.kind === "reject" ? t("platformAdmin.requests.reject") : t("platformAdmin.requests.revoke")}
        tone="danger" busy={!!busyId}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(r) => void confirm(r)} onCancel={() => setDialog(null)}
      />
    </div>
  );
}
