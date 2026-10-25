"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { approveTeacherRequest, listTeacherRequests, rejectTeacherRequest, setTeacherStatus } from "@/lib/lms/admin";
import type { TeacherRequestAdminOut, TeacherRequestStatus } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Pager } from "@/components/lms/Pager";
import { ReasonDialog } from "@/components/lms/admin/ReasonDialog";
import { UserStatusBadge } from "@/components/lms/admin/UserStatusBadge";
import { useAdminSummary } from "@/components/lms/admin/AdminShell";
import { fmtApiDateTime } from "@/lib/format"; // Phase 6 S4 (H2)

type Filter = TeacherRequestStatus | "all";
// Phase 6 S4 (admin M7): the teacher status a request status implies; a badge shows only when they differ.
const IMPLIED_TEACHER_STATUS: Record<string, string> = { pending: "pending", approved: "approved", rejected: "none", cancelled: "none" };
const FILTERS: Filter[] = ["pending", "approved", "rejected", "all"];

export default function TeacherRequestsPage() {
  const { lang, t } = useTranslation();
  const { refresh } = useAdminSummary();
  const [filter, setFilter] = useState<Filter>("pending");
  const [items, setItems] = useState<TeacherRequestAdminOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<{ kind: "reject" | "revoke"; req: TeacherRequestAdminOut } | null>(null);
  const [dialogError, setDialogError] = useState<unknown>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listTeacherRequests(filter, next);
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [filter]);
  useEffect(() => { void load(); }, [load]);

  const replace = (u: TeacherRequestAdminOut) => setItems((prev) => prev.map((r) => (r.id === u.id ? u : r)));

  const approve = async (r: TeacherRequestAdminOut) => {
    setBusyId(r.id);
    setError(null);
    try {
      await approveTeacherRequest(r.id);
      await load();
      refresh();
    } catch (e) {
      setError(e);
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
        await load();
        refresh();
      } else {
        await setTeacherStatus(dialog.req.user.id, "revoked", reason || undefined);
        replace({ ...dialog.req, user_teacher_status: "revoked" });
      }
      setDialog(null);
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold text-slate-900">{t("platformAdmin.requests.title")}</h1>
      <div role="group" aria-label={t("platformAdmin.requests.filter")} className="mb-4 flex flex-wrap gap-1">
        {FILTERS.map((f) => (
          <button key={f} type="button" aria-pressed={f === filter} onClick={() => setFilter(f)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${f === filter ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"}`}>
            {t(`platformAdmin.requests.filters.${f}`)}
          </button>
        ))}
      </div>
      {error ? <ErrorMessage error={error} onRetry={() => load()} className="mb-4" /> : null}
      {loading && items.length === 0 && !error && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{t("platformAdmin.requests.empty")}</p>
      )}
      <ul className="space-y-3">
        {items.map((r) => (
          <li key={r.id} className="rounded-2xl border border-slate-200 bg-white p-4 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-semibold text-slate-900">{r.user.display_name || r.user.email}</p>
                <p className="text-xs text-slate-500">{r.user.email}</p>
              </div>
              {/* --- Phase 6 S4 (admin M7): request status only; teacher status only when it differs, prefixed "Now:" --- */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">{t(`teacherRequest.requestStatus.${r.status}`)}</span>
                {r.user_teacher_status !== IMPLIED_TEACHER_STATUS[r.status] && (
                  <span className="inline-flex items-center gap-1 text-xs text-slate-600">
                    {t("organizations.adminUser.nowPrefix")} <UserStatusBadge kind="teacher" status={r.user_teacher_status} />
                  </span>
                )}
              </div>
            </div>
            <p className="mt-1 text-xs text-slate-500">{fmtApiDateTime(r.created_at, lang)}</p>
            <p className="mt-2 whitespace-pre-wrap text-slate-700">{r.message || t("platformAdmin.requests.noMessage")}</p>
            {r.reason && <p className="mt-2 text-slate-700"><strong>{t("teacherRequest.reason")}:</strong> {r.reason}</p>}
            {r.decided_by && r.decided_at && (
              <p className="mt-1 text-xs text-slate-500">{t("platformAdmin.requests.decidedBy", { name: r.decided_by.display_name || r.decided_by.email, date: fmtApiDateTime(r.decided_at, lang) })}</p>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              {r.status === "pending" && (
                <>
                  <button type="button" disabled={busyId === r.id} onClick={() => approve(r)}
                    className="rounded-xl bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50">{t("platformAdmin.requests.approve")}</button>
                  <button type="button" disabled={busyId === r.id} onClick={() => { setDialogError(null); setDialog({ kind: "reject", req: r }); }}
                    className="rounded-xl border border-red-300 px-3 py-1.5 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50">{t("platformAdmin.requests.reject")}</button>
                </>
              )}
              {r.user_teacher_status === "approved" && (
                <button type="button" disabled={busyId === r.id} onClick={() => { setDialogError(null); setDialog({ kind: "revoke", req: r }); }}
                  className="rounded-xl border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">{t("platformAdmin.requests.revoke")}</button>
              )}
            </div>
          </li>
        ))}
      </ul>
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
      <ReasonDialog
        open={!!dialog}
        title={dialog?.kind === "reject" ? t("platformAdmin.requests.rejectTitle") : t("platformAdmin.requests.revokeTitle")}
        body={dialog?.kind === "reject" ? t("platformAdmin.requests.rejectBody") : t("platformAdmin.requests.revokeBody")}
        confirmLabel={dialog?.kind === "reject" ? t("platformAdmin.requests.reject") : t("platformAdmin.requests.revoke")}
        danger optional={dialog?.kind === "revoke"} busy={!!busyId} error={dialogError}
        onConfirm={confirm} onCancel={() => setDialog(null)}
      />
    </div>
  );
}
