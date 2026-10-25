"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { disableUser, enableUser, getUser, setTeacherStatus } from "@/lib/lms/admin";
import type { AdminUserDetailOut } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { ReasonDialog } from "@/components/lms/admin/ReasonDialog";
import { UserStatusBadge } from "@/components/lms/admin/UserStatusBadge";
// --- Phase 6 S4 ---
import { SystemAccountBadge } from "@/components/lms/org/OrgUi";
import { isSystemAccount } from "@/lib/lms/organizations";
import { fmtApiDateTime } from "@/lib/format";
// --- Phase 6 S4 end ---

type Action = "disable" | "revoke" | "grant";

export default function AdminUserDetailPage() {
  const { userId } = useParams<{ userId: string }>();
  const { lang, t } = useTranslation();
  const { me } = useLmsMe();
  const [user, setUser] = useState<AdminUserDetailOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setUser(await getUser(userId));
    } catch (e) {
      setError(e);
    }
  }, [userId]);
  useEffect(() => { void load(); }, [load]);

  const run = async (reason: string) => {
    if (!user || !action) return;
    setBusy(true);
    setDialogError(null);
    try {
      if (action === "disable") await disableUser(user.id, reason);
      else await setTeacherStatus(user.id, action === "grant" ? "approved" : "revoked", reason || undefined);
      setAction(null);
      await load();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };
  const enable = async () => {
    if (!user) return;
    setError(null);
    try {
      await enableUser(user.id);
      await load();
    } catch (e) {
      setError(e);
    }
  };

  const back = <Link href={`/${lang}/admin/users`} className="text-sm font-medium text-brand-700 hover:underline">{t("platformAdmin.users.back")}</Link>;
  if (error && !user) return <div>{back}<ErrorMessage error={error} onRetry={load} className="mt-4" /></div>;
  if (!user) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;

  // --- Phase 6 S4 (admin M5, M8): system accounts are read-only; teacher status is a labelled row ---
  const system = isSystemAccount(user);
  const canDisable = user.id !== me?.id && !user.is_platform_admin && !system;
  // --- Phase 6 S4 end ---
  const btn = "rounded-xl border px-3 py-1.5 text-sm font-medium";
  const userName = user.display_name || user.email;
  return (
    <div>
      {back}
      <h1 className="mb-1 mt-2 text-2xl font-bold text-slate-900">{user.display_name || user.email}</h1>
      <p className="mb-4 text-sm text-slate-500">{user.email}</p>
      {error ? <ErrorMessage error={error} onRetry={load} className="mb-4" /> : null}
      <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 text-sm">
        {(system || user.is_platform_admin || user.disabled_at) && (
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {system && <SystemAccountBadge />}
            {user.is_platform_admin && <UserStatusBadge kind="account" status="admin" />}
            {user.disabled_at && <UserStatusBadge kind="account" status="disabled" />}
          </div>
        )}
        {system && <p className="mb-3 text-xs text-slate-600">{t("organizations.admin.systemAccountHint")}</p>}
        <dl className="grid gap-2 sm:grid-cols-2">
          <div><dt className="text-xs text-slate-500">{t("platformAdmin.users.teacherStatus")}</dt><dd>{user.teacher_status === "none" ? t("organizations.adminUser.notTeacher") : <UserStatusBadge kind="teacher" status={user.teacher_status} />}</dd></div>
          <div><dt className="text-xs text-slate-500">{t("organizations.adminUser.userId")}</dt><dd className="break-all font-mono text-xs">{user.id}</dd></div>
          <div><dt className="text-xs text-slate-500">{t("platformAdmin.users.created")}</dt><dd>{fmtApiDateTime(user.created_at, lang)}</dd></div>
          <div><dt className="text-xs text-slate-500">{t("platformAdmin.users.emailVerified")}</dt><dd>{user.email_verified ? t("platformAdmin.yes") : t("platformAdmin.no")}</dd></div>
          <div><dt className="text-xs text-slate-500">{t("platformAdmin.users.activeEnrollments")}</dt><dd>{user.active_enrollment_count}</dd></div>
          {user.disabled_at && (
            <div><dt className="text-xs text-slate-500">{t("platformAdmin.users.disabledReason")}</dt><dd>{user.disabled_reason || "—"}</dd></div>
          )}
        </dl>
        {!system && <div className="mt-4 flex flex-wrap gap-2">
          {user.teacher_status === "approved" ? (
            <button type="button" className={`${btn} border-slate-300 text-slate-700 hover:bg-slate-50`} onClick={() => { setDialogError(null); setAction("revoke"); }}>{t("platformAdmin.users.revokeTeacher")}</button>
          ) : (
            <button type="button" className={`${btn} border-emerald-300 text-emerald-700 hover:bg-emerald-50`} onClick={() => { setDialogError(null); setAction("grant"); }}>{t("platformAdmin.users.grantTeacher")}</button>
          )}
          {canDisable && (user.disabled_at ? (
            <button type="button" className={`${btn} border-slate-300 text-slate-700 hover:bg-slate-50`} onClick={enable}>{t("platformAdmin.users.enable")}</button>
          ) : (
            <button type="button" className={`${btn} border-red-300 text-red-700 hover:bg-red-50`} onClick={() => { setDialogError(null); setAction("disable"); }}>{t("platformAdmin.users.disable")}</button>
          ))}
        </div>}
      </div>

      <h2 className="mb-2 text-lg font-semibold text-slate-900">{t("platformAdmin.users.ownedCourses")}</h2>
      {user.owned_courses.length === 0 ? <p className="mb-6 text-sm text-slate-500">{t("platformAdmin.users.noCourses")}</p> : (
        <ul className="mb-6 divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white text-sm">
          {user.owned_courses.map((c) => (
            <li key={c.id} className="px-4 py-2">
              <Link href={`/${lang}/admin/courses/${c.id}`} className="font-medium text-brand-700 hover:underline">{pickLocalized(c.title, lang, c.default_language)}</Link>
            </li>
          ))}
        </ul>
      )}

      <h2 className="mb-2 text-lg font-semibold text-slate-900">{t("platformAdmin.users.requestHistory")}</h2>
      {user.teacher_requests.length === 0 ? <p className="text-sm text-slate-500">{t("teacherRequest.noHistory")}</p> : (
        <ul className="space-y-2">
          {user.teacher_requests.map((r) => (
            <li key={r.id} className="rounded-2xl border border-slate-200 bg-white p-3 text-sm">
              <div className="flex justify-between"><span className="font-semibold">{t(`teacherRequest.requestStatus.${r.status}`)}</span><time className="text-xs text-slate-500">{fmtApiDateTime(r.created_at, lang)}</time></div>
              {r.message && <p className="mt-1 whitespace-pre-wrap text-slate-700">{r.message}</p>}
              {r.reason && <p className="mt-1 text-slate-700"><strong>{t("teacherRequest.reason")}:</strong> {r.reason}</p>}
            </li>
          ))}
        </ul>
      )}

      <ReasonDialog
        open={!!action}
        title={action === "disable" ? t("platformAdmin.users.disableTitle") : action === "revoke" ? t("platformAdmin.users.revokeTitle") : t("platformAdmin.users.grantTitle")}
        body={`${t("organizations.adminUser.disableTarget", { name: userName })} ${action === "disable" ? t("platformAdmin.users.disableBody") : action === "revoke" ? t("platformAdmin.requests.revokeBody") : t("organizations.adminUser.grantBody")}`}
        confirmLabel={action === "disable" ? t("platformAdmin.users.disable") : action === "revoke" ? t("platformAdmin.requests.revoke") : t("platformAdmin.users.grantTeacher")}
        danger={action !== "grant"} optional={action !== "disable"} busy={busy} error={dialogError}
        onConfirm={run} onCancel={() => setAction(null)}
      />
    </div>
  );
}
