"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { disableUser, enableUser, getUser, setTeacherStatus } from "@/lib/lms/admin";
import type { AdminUserDetailOut } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import { isSystemAccount } from "@/lib/lms/organizations";
import { fmtApiDateTime } from "@/lib/format";
import { Badge, Button, Card, DescriptionList, LoadingState, PageHeader, ReasonDialog, toast } from "@/components/ui";
import { UserStatusBadge } from "@/components/lms/admin/UserStatusBadge";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { LoadError, OrgError, SystemAccountBadge } from "@/components/lms/org/OrgUi";
import { UserOrganizationsSection } from "@/components/lms/org/admin/UserOrganizationsSection"; // Phase 6 S4b

type Action = "disable" | "revoke" | "grant";

export default function AdminUserDetailPage() {
  const { userId } = useParams<{ userId: string }>();
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const { me } = useLmsMe();
  const [user, setUser] = useState<AdminUserDetailOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [enabling, setEnabling] = useState(false);
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

  const userName = user ? user.display_name || user.email : "";
  const run = async (reason: string) => {
    if (!user || !action) return;
    setBusy(true);
    setDialogError(null);
    try {
      if (action === "disable") await disableUser(user.id, reason);
      else await setTeacherStatus(user.id, action === "grant" ? "approved" : "revoked", reason || undefined);
      toast.success(t(action === "disable" ? "platformAdmin.toast.disabled" : action === "grant" ? "platformAdmin.toast.granted" : "platformAdmin.toast.revoked", { name: userName }));
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
    setEnabling(true);
    try {
      await enableUser(user.id);
      toast.success(t("platformAdmin.toast.enabled", { name: userName }));
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setEnabling(false);
    }
  };

  const usersCrumb = { label: t("platformAdmin.users.title"), href: `/${lang}/admin/users` };
  if (error && !user) {
    return (
      <div>
        <PageHeader title={t("platformAdmin.users.title")} breadcrumbs={crumbs(usersCrumb, { label: "…" })} />
        <LoadError error={error} onRetry={load} />
      </div>
    );
  }
  if (!user) return <LoadingState label={t("lms.common.loading")} />;

  // Phase 6 S4 (admin M5, M8): system accounts are read-only; teacher status is a labelled row.
  const system = isSystemAccount(user);
  const canDisable = user.id !== me?.id && !user.is_platform_admin && !system;
  const badges = (system || user.is_platform_admin || user.disabled_at) ? (
    <span className="flex flex-wrap items-center gap-2">
      {system && <SystemAccountBadge />}
      {user.is_platform_admin && <UserStatusBadge kind="account" status="admin" />}
      {user.disabled_at && <UserStatusBadge kind="account" status="disabled" />}
    </span>
  ) : undefined;
  const actions = !system ? (
    <>
      {user.teacher_status === "approved" ? (
        <Button variant="secondary" onClick={() => { setDialogError(null); setAction("revoke"); }}>{t("platformAdmin.users.revokeTeacher")}</Button>
      ) : (
        <Button variant="secondary" onClick={() => { setDialogError(null); setAction("grant"); }}>{t("platformAdmin.users.grantTeacher")}</Button>
      )}
      {canDisable && (user.disabled_at ? (
        <Button variant="secondary" loading={enabling} onClick={() => void enable()}>{t("platformAdmin.users.enable")}</Button>
      ) : (
        <Button variant="danger" onClick={() => { setDialogError(null); setAction("disable"); }}>{t("platformAdmin.users.disable")}</Button>
      ))}
    </>
  ) : undefined;

  return (
    <div>
      <PageHeader
        title={userName}
        description={user.display_name ? user.email : undefined}
        badge={badges}
        breadcrumbs={crumbs(usersCrumb, { label: userName })}
        secondaryActions={actions}
      />
      {error ? <OrgError error={error} onRetry={load} className="mb-4" /> : null}
      <Card className="mb-6">
        {system && <p className="mb-4 text-sm text-slate-700">{t("organizations.admin.systemAccountHint")}</p>}
        <DescriptionList twoColumns items={[
          { key: "teacher", term: t("platformAdmin.users.teacherStatus"), description: user.teacher_status === "none" ? t("organizations.adminUser.notTeacher") : <UserStatusBadge kind="teacher" status={user.teacher_status} /> },
          { key: "id", term: t("organizations.adminUser.userId"), description: <span className="break-all font-mono text-sm">{user.id}</span> },
          { key: "created", term: t("platformAdmin.users.created"), description: fmtApiDateTime(user.created_at, lang) },
          { key: "verified", term: t("platformAdmin.users.emailVerified"), description: user.email_verified ? t("platformAdmin.yes") : t("platformAdmin.no") },
          { key: "enrollments", term: t("platformAdmin.users.activeEnrollments"), description: user.active_enrollment_count },
          ...(user.disabled_at ? [{ key: "reason", term: t("platformAdmin.users.disabledReason"), description: user.disabled_reason || "—" }] : []),
        ]} />
      </Card>

      {/* Phase 6 S4b: organizations and roles, add to organization */}
      <UserOrganizationsSection user={user} readOnly={system} />

      <Card className="mb-6" title={t("platformAdmin.users.ownedCourses")} padding={user.owned_courses.length ? "none" : "md"}>
        {user.owned_courses.length === 0 ? <p className="text-sm text-slate-600">{t("platformAdmin.users.noCourses")}</p> : (
          <ul className="divide-y divide-slate-100 border-t border-slate-100">
            {user.owned_courses.map((c) => (
              <li key={c.id} className="px-4 py-3 sm:px-6">
                <Link href={`/${lang}/admin/courses/${c.id}`} className="inline-flex min-h-11 items-center font-medium text-brand-700 hover:underline sm:min-h-0">
                  {pickLocalized(c.title, lang, c.default_language)}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title={t("platformAdmin.users.requestHistory")} padding={user.teacher_requests.length ? "none" : "md"}>
        {user.teacher_requests.length === 0 ? <p className="text-sm text-slate-600">{t("teacherRequest.noHistory")}</p> : (
          <ul className="divide-y divide-slate-100 border-t border-slate-100">
            {user.teacher_requests.map((r) => (
              <li key={r.id} className="px-4 py-3 text-sm sm:px-6">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Badge>{t(`teacherRequest.requestStatus.${r.status}`)}</Badge>
                  <time className="text-sm text-slate-600">{fmtApiDateTime(r.created_at, lang)}</time>
                </div>
                {r.message && <p className="mt-2 whitespace-pre-wrap break-words text-slate-800">{r.message}</p>}
                {r.reason && <p className="mt-1 break-words text-slate-800"><strong>{t("teacherRequest.reason")}:</strong> {r.reason}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <ReasonDialog
        open={!!action}
        title={action === "disable" ? t("platformAdmin.users.disableTitle") : action === "revoke" ? t("platformAdmin.users.revokeTitle") : t("platformAdmin.users.grantTitle")}
        object={user.display_name ? `${user.display_name} · ${user.email}` : user.email}
        effect={action === "disable" ? t("platformAdmin.users.disableBody") : action === "revoke" ? t("platformAdmin.requests.revokeBody") : t("organizations.adminUser.grantBody")}
        confirmLabel={action === "disable" ? t("platformAdmin.users.disable") : action === "revoke" ? t("platformAdmin.requests.revoke") : t("platformAdmin.users.grantTeacher")}
        tone={action === "grant" ? "primary" : "danger"} optional={action !== "disable"} busy={busy}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(r) => void run(r)} onCancel={() => setAction(null)}
      />
    </div>
  );
}
