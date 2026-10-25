"use client";

import React, { useCallback, useState } from "react";
import { UserPlus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { listOrgMembers, memberMatches, removeOrgMember, type OrgMemberOut } from "@/lib/lms/organizations";
import {
  listOrgInvitations, resendOrgInvitation, revokeOrgInvitation, type InvitationOut,
} from "@/lib/lms/invitations";
import { fmtApiDate } from "@/lib/format";
import {
  Button, ConfirmDialog, EmptyState, PageHeader, ReasonDialog, SearchInput, Table, toast, type TableColumn,
} from "@/components/ui";
import { useOrg } from "@/components/lms/org/OrgShell";
import { InviteDialog, toastInvitationSent } from "@/components/lms/org/InviteDialog";
import { OrgBadge, OrgError } from "@/components/lms/org/OrgUi";
import { useCursorList, useDebounced } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";

export default function OrgTeachersPage() {
  const { lang, t } = useTranslation();
  const { me } = useLmsMe();
  const { org, readOnly, reload, crumbs } = useOrg();
  const [input, setInput] = useState("");
  const q = useDebounced(input);
  const fetchMembers = useCallback((cursor: string | null) => listOrgMembers(org.id, { state: "active", cursor }), [org.id]);
  const members = useCursorList(fetchMembers);
  // The members endpoint has no text filter: search the loaded rows.
  const shown = members.items.filter((m) => memberMatches(m, q));
  const membersState = useTableState(members, shown.length);
  const fetchInvites = useCallback((cursor: string | null) => listOrgInvitations(org.id, { cursor }), [org.id]);
  const invites = useCursorList(fetchInvites);
  const invitesState = useTableState(invites);
  const [inviting, setInviting] = useState(false);
  const [removing, setRemoving] = useState<OrgMemberOut | null>(null);
  const [revoking, setRevoking] = useState<InvitationOut | null>(null);
  const [resendingId, setResendingId] = useState<string | null>(null);
  const [resendError, setResendError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);

  const doRemove = async (reason: string) => {
    if (!removing) return;
    setBusy(true);
    setDialogError(null);
    try {
      await removeOrgMember(org.id, removing.user.id, reason);
      toast.success(t("organizations.members.removed", { name: removing.user.display_name || removing.user.email }));
      setRemoving(null);
      await Promise.all([members.reload(), reload()]);
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };
  const doRevoke = async () => {
    if (!revoking) return;
    setBusy(true);
    setDialogError(null);
    try {
      await revokeOrgInvitation(org.id, revoking.id);
      toast.success(t("invitations.revoked", { email: revoking.email }));
      setRevoking(null);
      await invites.reload();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };
  const resend = async (i: InvitationOut) => {
    setResendError(null);
    setResendingId(i.id);
    try {
      await resendOrgInvitation(org.id, i.id);
      toast.success(t("invitations.resent", { email: i.email }));
      await invites.reload();
    } catch (e) {
      setResendError(e);
    } finally {
      setResendingId(null);
    }
  };

  const memberTone = (m: OrgMemberOut) => (m.state === "active" ? "active" : "removed");
  const memberColumns: TableColumn<OrgMemberOut>[] = [
    {
      key: "person", header: t("organizations.members.person"), primary: true, className: "sm:min-w-[14rem]",
      cell: (m) => <>{m.user.display_name || m.user.email}<span className="block text-sm font-normal text-slate-600 [overflow-wrap:anywhere]">{m.user.email}</span></>,
    },
    { key: "role", header: t("organizations.adminUser.role"), cell: (m) => t(`organizations.roles.${m.role}`) },
    { key: "state", header: t("organizations.admin.status"), cell: (m) => <OrgBadge tone={memberTone(m)} labelKey={`organizations.members.state.${memberTone(m)}`} /> },
    { key: "since", header: t("organizations.members.sinceColumn"), nowrap: true, cell: (m) => fmtApiDate(m.created_at, lang) },
    {
      key: "actions", header: "", actions: true, align: "right",
      cell: (m) => m.user.id === me?.id ? null : (
        <Button variant="secondary" size="sm" disabled={readOnly} onClick={() => { setDialogError(null); setRemoving(m); }}>
          {t("organizations.members.remove")}
        </Button>
      ),
    },
  ];
  const inviteColumns: TableColumn<InvitationOut>[] = [
    { key: "email", header: t("invitations.dialog.email"), primary: true, className: "sm:min-w-[14rem]", cell: (i) => <span className="[overflow-wrap:anywhere]">{i.email}</span> },
    { key: "role", header: t("organizations.adminUser.role"), cell: (i) => t(`invitations.roles.${i.role}`) },
    { key: "state", header: t("organizations.admin.status"), cell: (i) => <OrgBadge tone={i.state === "pending" ? "invited" : i.state} labelKey={`invitations.state.${i.state}`} /> },
    {
      key: "sent", header: t("invitations.sentColumn"), className: "sm:min-w-[13rem]",
      cell: (i) => (
        <>
          {t("invitations.sentBy", { name: i.invited_by_name || "—", date: fmtApiDate(i.created_at, lang) })}
          {i.state === "pending" && <span className="block text-sm text-slate-600">{t("invitations.expiresOn", { date: fmtApiDate(i.expires_at, lang) })}</span>}
        </>
      ),
    },
    {
      key: "actions", header: "", actions: true, align: "right",
      cell: (i) => (i.state === "pending" || i.state === "expired") ? (
        <span className="flex flex-wrap justify-end gap-2 lg:flex-nowrap">
          <Button variant="secondary" size="sm" disabled={readOnly} loading={resendingId === i.id} onClick={() => void resend(i)}>{t("invitations.resend")}</Button>
          {i.state === "pending" && (
            <Button variant="secondary" size="sm" disabled={readOnly} onClick={() => { setDialogError(null); setRevoking(i); }}>{t("invitations.revoke")}</Button>
          )}
        </span>
      ) : null,
    },
  ];
  const inviteButton = (variant: "primary" | "secondary") => (
    <Button variant={variant} disabled={readOnly} leftIcon={<UserPlus aria-hidden="true" className="h-4 w-4" />} onClick={() => setInviting(true)}>
      {t("invitations.inviteTeacher")}
    </Button>
  );
  const removingName = removing ? removing.user.display_name || removing.user.email : "";
  return (
    <div>
      <PageHeader title={t("organizations.members.title")} breadcrumbs={crumbs({ label: t("organizations.org.nav.teachers") })} primaryAction={inviteButton("primary")} />
      <section aria-labelledby="t-members" className="mb-10">
        <h2 id="t-members" className="sr-only">{t("organizations.members.title")}</h2>
        <Table
          caption={t("organizations.members.title")}
          columns={memberColumns}
          rows={shown}
          rowKey={(m) => m.user.id}
          {...membersState}
          search={<SearchInput value={input} onChange={setInput} label={t("lms.common.search")} placeholder={t("organizations.members.searchPlaceholder")} containerClassName="sm:max-w-sm" />}
          empty={
            <EmptyState
              title={q ? t("organizations.members.emptySearch") : t("organizations.members.empty")}
              action={!q && !readOnly ? inviteButton("secondary") : undefined}
            />
          }
        />
        <MoreError list={members} />
      </section>

      <section aria-labelledby="t-invites">
        <h2 id="t-invites" className="mb-3 text-lg font-semibold leading-7 text-slate-900">{t("invitations.title")}</h2>
        {resendError ? <OrgError error={resendError} className="mb-3" /> : null}
        <Table
          caption={t("invitations.title")}
          columns={inviteColumns}
          rows={invites.items}
          rowKey={(i) => i.id}
          {...invitesState}
          empty={<EmptyState title={t("invitations.empty")} />}
        />
        <MoreError list={invites} />
      </section>

      <InviteDialog open={inviting} orgId={org.id} orgName={org.name} onClose={() => setInviting(false)}
        onSent={(inv, email) => { setInviting(false); toastInvitationSent(t, inv, email); void invites.reload(); void reload(); }} />
      <ReasonDialog
        open={!!removing}
        title={t("organizations.members.removeTitle", { name: removingName })}
        object={removing ? (removing.user.display_name ? `${removing.user.display_name} · ${removing.user.email}` : removing.user.email) : undefined}
        effect={t("organizations.members.removeBody", { name: removingName, org: org.name })}
        confirmLabel={t("organizations.members.remove")} tone="danger" busy={busy}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(r) => void doRemove(r)} onCancel={() => setRemoving(null)}
      />
      <ConfirmDialog
        open={!!revoking}
        title={t("invitations.revokeTitle")}
        object={revoking?.email}
        effect={t("invitations.revokeBody", { email: revoking?.email || "" })}
        confirmLabel={t("invitations.revoke")} tone="danger" busy={busy}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={() => void doRevoke()} onCancel={() => setRevoking(null)}
      />
    </div>
  );
}
