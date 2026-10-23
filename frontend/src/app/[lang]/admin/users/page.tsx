"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { disableUser, enableUser, listUsers } from "@/lib/lms/admin";
import type { AdminUserOut, TeacherStatus } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Pager } from "@/components/lms/Pager";
import { ReasonDialog } from "@/components/lms/admin/ReasonDialog";
import { UserStatusBadge } from "@/components/lms/admin/UserStatusBadge";

const STATUSES: (TeacherStatus | "")[] = ["", "none", "pending", "approved", "revoked"];

export default function AdminUsersPage() {
  const { lang, t } = useTranslation();
  const { me } = useLmsMe();
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<TeacherStatus | "">("");
  const [disabledOnly, setDisabledOnly] = useState(false);
  const [items, setItems] = useState<AdminUserOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [target, setTarget] = useState<AdminUserOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);

  useEffect(() => {
    const h = setTimeout(() => setQ(input.trim()), 350);
    return () => clearTimeout(h);
  }, [input]);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listUsers({ q, teacher_status: status, disabled: disabledOnly ? true : undefined, cursor: next });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [q, status, disabledOnly]);
  useEffect(() => { void load(); }, [load]);

  const replace = (u: AdminUserOut) => setItems((prev) => prev.map((x) => (x.id === u.id ? u : x)));

  const doDisable = async (reason: string) => {
    if (!target) return;
    setBusy(true);
    setDialogError(null);
    try {
      replace(await disableUser(target.id, reason));
      setTarget(null);
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };
  const doEnable = async (u: AdminUserOut) => {
    setError(null);
    try {
      replace(await enableUser(u.id));
    } catch (e) {
      setError(e);
    }
  };

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold text-slate-900">{t("platformAdmin.users.title")}</h1>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="u-q" className="block text-xs font-medium text-slate-600">{t("lms.common.search")}</label>
          <input id="u-q" value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("platformAdmin.users.searchPlaceholder")}
            className="w-64 rounded-xl border border-slate-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label htmlFor="u-st" className="block text-xs font-medium text-slate-600">{t("platformAdmin.users.teacherStatus")}</label>
          <select id="u-st" value={status} onChange={(e) => setStatus(e.target.value as TeacherStatus | "")}
            className="rounded-xl border border-slate-300 px-3 py-2 text-sm">
            {STATUSES.map((s) => <option key={s} value={s}>{s ? t(`platformAdmin.teacherStatus.${s}`) : t("platformAdmin.users.anyStatus")}</option>)}
          </select>
        </div>
        <label className="flex items-center gap-2 pb-2 text-sm text-slate-700">
          <input type="checkbox" checked={disabledOnly} onChange={(e) => setDisabledOnly(e.target.checked)} />
          {t("platformAdmin.users.disabledOnly")}
        </label>
      </div>
      {error ? <ErrorMessage error={error} onRetry={() => load()} className="mb-4" /> : null}
      {loading && items.length === 0 && !error && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{t("platformAdmin.users.empty")}</p>
      )}
      {items.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2">{t("platformAdmin.users.user")}</th>
                <th className="px-3 py-2">{t("platformAdmin.users.teacherStatus")}</th>
                <th className="px-3 py-2">{t("platformAdmin.users.account")}</th>
                <th className="px-3 py-2">{t("platformAdmin.users.created")}</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((u) => {
                const canToggle = u.id !== me?.id && !u.is_platform_admin;
                return (
                  <tr key={u.id}>
                    <td className="px-3 py-2">
                      <Link href={`/${lang}/admin/users/${u.id}`} className="font-medium text-brand-700 hover:underline">{u.display_name || u.email}</Link>
                      <p className="text-xs text-slate-500">{u.email}</p>
                    </td>
                    <td className="px-3 py-2"><UserStatusBadge kind="teacher" status={u.teacher_status} /></td>
                    <td className="space-x-1 px-3 py-2">
                      {u.is_platform_admin && <UserStatusBadge kind="account" status="admin" />}
                      {u.disabled_at && <UserStatusBadge kind="account" status="disabled" />}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">{new Date(u.created_at).toLocaleDateString(lang)}</td>
                    <td className="px-3 py-2 text-right">
                      {canToggle && (u.disabled_at ? (
                        <button type="button" onClick={() => doEnable(u)} className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium hover:bg-slate-50">{t("platformAdmin.users.enable")}</button>
                      ) : (
                        <button type="button" onClick={() => { setDialogError(null); setTarget(u); }} className="rounded-lg border border-red-300 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50">{t("platformAdmin.users.disable")}</button>
                      ))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
      <ReasonDialog open={!!target} title={t("platformAdmin.users.disableTitle")} body={t("platformAdmin.users.disableBody")}
        confirmLabel={t("platformAdmin.users.disable")} danger busy={busy} error={dialogError}
        onConfirm={doDisable} onCancel={() => setTarget(null)} />
    </div>
  );
}
