"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { adminCancelEmailChange, adminChangeEmail, correctAgeBand, disableUser, enableUser, getUser, sendPasswordReset, setTeacherStatus } from "@/lib/lms/admin";
import type { AdminUserDetailOut, LinkedAccountOut } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import { isSystemAccount } from "@/lib/lms/organizations";
import { fmtApiDate, fmtApiDateTimeShort } from "@/lib/format";
import { Badge, Button, Card, DescriptionList, LoadingState, PageHeader, STAFF_WIDTH, type MenuGroup, ReasonDialog, toast } from "@/components/ui";
import { UserStatusBadge } from "@/components/lms/admin/UserStatusBadge";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { LoadError, OrgError, SystemAccountBadge } from "@/components/lms/org/OrgUi";
import { UserOrganizationsSection } from "@/components/lms/org/admin/UserOrganizationsSection"; // Phase 6 S4b
import { CodeReasonDialog } from "@/components/lms/admin/CodeReasonDialog";
import { UserAccessSection } from "@/components/lms/access/UserAccessSection"; // S3 access
import { endUserSessions, setPlatformAdmin } from "@/lib/lms/security";
import { AgeBandDialog, AttemptLookupSection, ChangeEmailDialog } from "@/components/lms/admin/PersonParts"; // S4

type Action = "disable" | "revoke" | "grant" | "endSessions" | "resetPassword";
type PersonDialog = "changeEmail" | "correctAge" | "cancelEmail"; // S4
type AdminAction = "makeAdmin" | "removeAdmin";

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
  const [adminAction, setAdminAction] = useState<AdminAction | null>(null); // S1
  const [personDialog, setPersonDialog] = useState<PersonDialog | null>(null); // S4

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
      else if (action === "endSessions") await endUserSessions(user.id, reason);
      else if (action === "resetPassword") await sendPasswordReset(user.id, reason); // S4
      else await setTeacherStatus(user.id, action === "grant" ? "approved" : "revoked", reason || undefined);
      if (action === "resetPassword") toast.success(t("person.resetDone", { email: user.email }));
      else toast.success(t(action === "disable" ? "platformAdmin.toast.disabled" : action === "endSessions" ? "adminSecurity.toast.sessionsEnded" : action === "grant" ? "platformAdmin.toast.granted" : "platformAdmin.toast.revoked", { name: userName }));
      setAction(null);
      await load();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };
  const runAdmin = async (reason: string, code: string) => {
    if (!user || !adminAction) return;
    setBusy(true);
    setDialogError(null);
    try {
      await setPlatformAdmin(user.id, adminAction === "makeAdmin", reason, code);
      toast.success(t(adminAction === "makeAdmin" ? "adminSecurity.toast.adminGranted" : "adminSecurity.toast.adminRemoved", { name: userName }));
      setAdminAction(null);
      await load();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };
  // S4: the change-email and age dialogs
  const runPerson = async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true);
    setDialogError(null);
    try {
      await fn();
      toast.success(done);
      setPersonDialog(null);
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
  const primary = !system ? (
    user.teacher_status === "approved" ? (
      <Button variant="secondary" onClick={() => { setDialogError(null); setAction("revoke"); }}>{t("platformAdmin.users.revokeTeacher")}</Button>
    ) : (
      <Button variant="secondary" onClick={() => { setDialogError(null); setAction("grant"); }}>{t("platformAdmin.users.grantTeacher")}</Button>
    )
  ) : undefined;
  const overflow: MenuGroup[] | undefined = !system ? [
          { id: "sessions", items: [{ id: "endSessions", label: t("adminSecurity.user.endSessions") }] },
          // S4: one person's problem (a disabled or deleted account gets neither; an admin changes their own address)
          ...(!user.disabled_at && !user.deleted ? [{ id: "person", items: [
            { id: "resetPassword", label: t("person.resetPassword") },
            ...(!user.is_platform_admin ? [{ id: "changeEmail", label: t("person.changeEmail") }] : []),
            { id: "correctAge", label: t("person.correctAge") },
          ] }] : []),
          // S1: platform admins, confirmed with the acting admin's code
          { id: "admin", items: [user.is_platform_admin
            ? { id: "removeAdmin", label: t("adminSecurity.user.removeAdmin"), danger: true }
            : { id: "makeAdmin", label: t("adminSecurity.user.makeAdmin") }] },
          ...(canDisable ? [{ id: "account", items: [user.disabled_at
            ? { id: "enable", label: t("platformAdmin.users.enable") }
            : { id: "disable", label: t("platformAdmin.users.disable"), danger: true }] }] : []),
        ] : undefined;
  const onOverflow = (id: string) => {
          setDialogError(null);
          if (id === "enable") void enable();
          else if (id === "makeAdmin" || id === "removeAdmin") setAdminAction(id);
          else if (id === "endSessions" || id === "disable" || id === "resetPassword") setAction(id);
          else if (id === "changeEmail" || id === "correctAge") setPersonDialog(id);
        };

  return (
    <div className={`w-full ${STAFF_WIDTH.list}`}>
      <PageHeader
        title={userName}
        description={user.display_name ? user.email : undefined}
        badge={badges}
        breadcrumbs={crumbs(usersCrumb, { label: userName })}
        primaryAction={primary}
        overflow={overflow}
        onOverflow={onOverflow}
        overflowLabel={t("coursePage.moreActions")}
      />
      {error ? <OrgError error={error} onRetry={load} className="mb-4" /> : null}
      <Card className="mb-6">
        {system && <p className="mb-4 text-sm text-slate-700">{t("organizations.admin.systemAccountHint")}</p>}
        <DescriptionList twoColumns items={[
          { key: "teacher", term: t("platformAdmin.users.teacherStatus"), description: user.teacher_status === "none" ? t("organizations.adminUser.notTeacher") : <UserStatusBadge kind="teacher" status={user.teacher_status} /> },
          { key: "id", term: t("organizations.adminUser.userId"), description: <span className="break-all font-mono text-sm">{user.id}</span> },
          { key: "created", term: t("platformAdmin.users.created"), description: fmtApiDateTimeShort(user.created_at, lang) },
          { key: "verified", term: t("platformAdmin.users.emailVerified"), description: user.email_verified ? t("platformAdmin.yes") : t("platformAdmin.no") },
          // S4 person page
          { key: "login", term: t("person.lastLogin"), description: user.last_login_at ? fmtApiDateTimeShort(user.last_login_at, lang) : t("person.never") },
          { key: "age", term: t("person.age"), description: user.age_band ? t(`privacy.age.${user.age_band}`) : t("person.ageUnknown") },
          { key: "consent", term: t("person.consent"), description: user.consent_state
            ? `${t(`person.consentState.${user.consent_state}`)}${user.consent_state === "pending_guardian" && user.consent_due_at ? ` (${t("person.consentDue", { date: fmtApiDate(user.consent_due_at, lang) })})` : ""}`
            : "—" },
          ...(user.parent_links ? [
            { key: "parents", term: t("person.parents"), description: <LinkedNames lang={lang} items={user.parent_links.parents} count={user.parent_links.parents_count} /> },
            ...(user.parent_links.children_count ? [{ key: "children", term: t("person.children"), description: <LinkedNames lang={lang} items={user.parent_links.children} count={user.parent_links.children_count} /> }] : []),
          ] : []),
          ...(user.pending_email_change ? [{ key: "pendingEmail", term: t("person.pendingEmail"), description: (
            <span className="break-all">
              {t("person.pendingEmailValue", { email: user.pending_email_change.new_email, date: fmtApiDateTimeShort(user.pending_email_change.expires_at, lang) })}
              {user.pending_email_change.by_admin ? ` · ${t("person.pendingByAdmin")}` : ""}
              {!system && (
                <Button variant="link" size="sm" className="ml-2 text-danger-700" onClick={() => { setDialogError(null); setPersonDialog("cancelEmail"); }}>
                  {t("person.cancelEmail")}
                </Button>
              )}
            </span>
          ) }] : []),
          // item 3: the password and the linked Google / Apple accounts
          ...(user.sign_in_methods ? [{ key: "signIn", term: t("person.signInMethods"), description: user.sign_in_methods.length
            ? user.sign_in_methods.map((m) => m.linked_at
              ? t(`person.signInMethod.${m.method}Linked`, { date: fmtApiDate(m.linked_at, lang) })
              : t(`person.signInMethod.${m.method}`)).join(" · ")
            : t("person.linksNone") }] : []),
          ...(user.is_platform_admin ? [{ key: "mfa", term: t("adminSecurity.user.mfa"), description: user.mfa_enabled ? t("adminSecurity.on") : t("adminSecurity.off") }] : []),
          { key: "enrollments", term: t("platformAdmin.users.activeEnrollments"), description: user.active_enrollment_count },
          ...(user.disabled_at ? [{ key: "reason", term: t("platformAdmin.users.disabledReason"), description: user.disabled_reason || "—" }] : []),
        ]} />
      </Card>

      {/* S3 access: exam passes, give and revoke (right after the summary: what the admin looks up most for a student) */}
      <UserAccessSection userId={user.id} name={user.display_name ? `${user.display_name} · ${user.email}` : user.email} readOnly={system} />

      {/* S4: the person's attempts, status only (never answers, scores or grades) */}
      <AttemptLookupSection userId={user.id} />

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
                  <time className="text-sm text-slate-600">{fmtApiDateTimeShort(r.created_at, lang)}</time>
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
        title={action === "resetPassword" ? t("person.resetTitle") : action === "disable" ? t("platformAdmin.users.disableTitle") : action === "endSessions" ? t("adminSecurity.user.endSessionsTitle") : action === "revoke" ? t("platformAdmin.users.revokeTitle") : t("platformAdmin.users.grantTitle")}
        object={user.display_name ? `${user.display_name} · ${user.email}` : user.email}
        effect={action === "resetPassword" ? t("person.resetBody") : action === "disable" ? t("platformAdmin.users.disableBody") : action === "endSessions" ? t("adminSecurity.user.endSessionsBody") : action === "revoke" ? t("platformAdmin.users.revokeImpact", { students: user.revoke_impact.students, courses: user.revoke_impact.courses }) : t("organizations.adminUser.grantBody")}
        confirmLabel={action === "resetPassword" ? t("person.resetSend") : action === "disable" ? t("platformAdmin.users.disable") : action === "endSessions" ? t("adminSecurity.user.endSessions") : action === "revoke" ? t("platformAdmin.requests.revoke") : t("platformAdmin.users.grantTeacher")}
        tone={action === "grant" || action === "resetPassword" ? "primary" : "danger"} optional={action === "grant"} busy={busy}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(r) => void run(r)} onCancel={() => setAction(null)}
      />
      <ChangeEmailDialog open={personDialog === "changeEmail"} name={user.display_name ? `${user.display_name} · ${user.email}` : user.email}
        busy={busy} error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(email, reason) => void runPerson(() => adminChangeEmail(user.id, email, reason), t("person.changeEmailDone", { email }))}
        onCancel={() => setPersonDialog(null)} />
      <AgeBandDialog open={personDialog === "correctAge"} name={user.display_name ? `${user.display_name} · ${user.email}` : user.email}
        current={user.age_band} busy={busy} error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(band, reason) => void runPerson(() => correctAgeBand(user.id, band, reason), t("person.ageDone"))}
        onCancel={() => setPersonDialog(null)} />
      <ReasonDialog open={personDialog === "cancelEmail"} title={t("person.cancelEmailTitle")}
        object={user.pending_email_change?.new_email} effect={t("person.cancelEmailBody")}
        confirmLabel={t("person.cancelEmail")} tone="danger" busy={busy}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(reason) => void runPerson(() => adminCancelEmailChange(user.id, reason), t("person.cancelEmailDone"))}
        onCancel={() => setPersonDialog(null)} />
      <CodeReasonDialog
        open={!!adminAction}
        title={adminAction === "makeAdmin" ? t("adminSecurity.user.makeAdminTitle") : t("adminSecurity.user.removeAdminTitle")}
        object={user.display_name ? `${user.display_name} · ${user.email}` : user.email}
        effect={adminAction === "makeAdmin" ? t("adminSecurity.user.makeAdminBody") : t("adminSecurity.user.removeAdminBody")}
        confirmLabel={adminAction === "makeAdmin" ? t("adminSecurity.user.makeAdmin") : t("adminSecurity.user.removeAdmin")}
        tone={adminAction === "makeAdmin" ? "primary" : "danger"} busy={busy}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(r, c) => void runAdmin(r, c)} onCancel={() => setAdminAction(null)}
      />
    </div>
  );
}

/** S4: the linked accounts' display names (each opens their person page), "and N more" past the shown ones. */
function LinkedNames({ lang, items, count }: { lang: string; items: LinkedAccountOut[]; count: number }) {
  const { t } = useTranslation();
  if (count === 0) return <>{t("person.linksNone")}</>;
  return (
    <span className="flex flex-wrap gap-x-2 gap-y-1">
      {items.map((p) => (
        <Link key={p.id} href={`/${lang}/admin/users/${p.id}`} className="text-brand-700 hover:underline">{p.display_name || t("person.noName")}</Link>
      ))}
      {count > items.length && <span className="text-slate-600">{t("person.linksMore", { count: count - items.length })}</span>}
    </span>
  );
}
