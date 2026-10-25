"use client";

import React, { useCallback, useEffect, useState } from "react";
import { UserPlus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { listOrgMembers, removeOrgMember, type OrgMemberOut } from "@/lib/lms/organizations";
import {
  listOrgInvitations, resendOrgInvitation, revokeOrgInvitation, type InvitationOut,
} from "@/lib/lms/invitations";
import { fmtApiDate } from "@/lib/format";
import { useOrg } from "@/components/lms/org/OrgShell";
import { InviteDialog } from "@/components/lms/org/InviteDialog";
import { EmptyBox, Loading, OrgBadge, OrgError, btn, inputCls, labelCls } from "@/components/lms/org/OrgUi";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { Pager } from "@/components/lms/Pager";
import { ReasonDialog } from "@/components/lms/admin/ReasonDialog";
import { toast } from "@/components/ui/Toast";

export default function OrgTeachersPage() {
  const { lang, t } = useTranslation();
  const { me } = useLmsMe();
  const { org, readOnly, reload } = useOrg();
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [members, setMembers] = useState<OrgMemberOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [invites, setInvites] = useState<InvitationOut[]>([]);
  const [invCursor, setInvCursor] = useState<string | null>(null);
  const [invLoading, setInvLoading] = useState(true);
  const [invError, setInvError] = useState<unknown>(null);
  const [inviting, setInviting] = useState(false);
  const [removing, setRemoving] = useState<OrgMemberOut | null>(null);
  const [revoking, setRevoking] = useState<InvitationOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);

  useEffect(() => {
    const h = setTimeout(() => setQ(input.trim()), 350);
    return () => clearTimeout(h);
  }, [input]);

  const loadMembers = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listOrgMembers(org.id, { q, state: "active", cursor: next });
      setMembers((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [org.id, q]);
  useEffect(() => { void loadMembers(); }, [loadMembers]);

  const loadInvites = useCallback(async (next?: string | null) => {
    setInvLoading(true);
    setInvError(null);
    try {
      const page = await listOrgInvitations(org.id, { cursor: next });
      setInvites((prev) => (next ? [...prev, ...page.items] : page.items));
      setInvCursor(page.next_cursor);
    } catch (e) {
      setInvError(e);
    } finally {
      setInvLoading(false);
    }
  }, [org.id]);
  useEffect(() => { void loadInvites(); }, [loadInvites]);

  const doRemove = async (reason: string) => {
    if (!removing) return;
    setBusy(true);
    setDialogError(null);
    try {
      await removeOrgMember(org.id, removing.user_id, reason);
      toast.success(t("organizations.members.removed", { name: removing.display_name || removing.email }));
      setRemoving(null);
      await Promise.all([loadMembers(), reload()]);
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
      await loadInvites();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };
  const resend = async (i: InvitationOut) => {
    setInvError(null);
    try {
      await resendOrgInvitation(org.id, i.id);
      toast.success(t("invitations.resent", { email: i.email }));
      await loadInvites();
    } catch (e) {
      setInvError(e);
    }
  };

  const memberTone = (m: OrgMemberOut) => (m.disabled ? "blocked" : m.state === "active" ? "active" : "removed");
  const memberLabel = (m: OrgMemberOut) => `organizations.members.state.${memberTone(m)}`;
  return (
    <div className="space-y-8">
      <section aria-labelledby="t-members">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 id="t-members" className="text-xl font-semibold text-slate-900">{t("organizations.members.title")}</h2>
          <button type="button" className={btn.primary} disabled={readOnly} onClick={() => setInviting(true)}>
            <UserPlus className="h-4 w-4" aria-hidden="true" />{t("invitations.inviteTeacher")}
          </button>
        </div>
        <div className="mb-3 w-full sm:w-72">
          <label htmlFor="m-q" className={labelCls}>{t("lms.common.search")}</label>
          <input id="m-q" value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("organizations.members.searchPlaceholder")} className={inputCls} />
        </div>
        {error ? <OrgError error={error} onRetry={() => loadMembers()} className="mb-3" /> : null}
        {loading && members.length === 0 && !error && <Loading />}
        {!loading && !error && members.length === 0 && (
          <EmptyBox text={q ? t("organizations.members.emptySearch") : t("organizations.members.empty")}>
            {!q && !readOnly && <button type="button" className={btn.secondary} onClick={() => setInviting(true)}>{t("invitations.inviteTeacher")}</button>}
          </EmptyBox>
        )}
        {members.length > 0 && (
          <>
            <p className="mb-2 text-xs text-slate-500">{t("organizations.members.shown", { n: members.length })}</p>
            <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white text-sm">
              {members.map((m) => {
                const self = m.user_id === me?.id;
                return (
                  <li key={m.user_id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
                    <div className="min-w-0 flex-1 basis-56">
                      <p className="truncate font-medium text-slate-900">{m.display_name || m.email}</p>
                      <p className="truncate text-xs text-slate-500">{m.email}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs text-slate-600">{t(`organizations.roles.${m.role}`)}</span>
                      <OrgBadge tone={memberTone(m)} labelKey={memberLabel(m)} />
                      {typeof m.course_count === "number" && <span className="text-xs text-slate-500">{t("organizations.members.courses", { n: m.course_count })}</span>}
                    </div>
                    {!self && (
                      <button type="button" className={btn.smallDanger} disabled={readOnly}
                        onClick={() => { setDialogError(null); setRemoving(m); }}>
                        {t("organizations.members.remove")}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          </>
        )}
        <Pager nextCursor={cursor} loading={loading} onMore={() => loadMembers(cursor)} />
      </section>

      <section aria-labelledby="t-invites">
        <h2 id="t-invites" className="mb-3 text-xl font-semibold text-slate-900">{t("invitations.title")}</h2>
        {invError ? <OrgError error={invError} onRetry={() => loadInvites()} className="mb-3" /> : null}
        {invLoading && invites.length === 0 && !invError && <Loading />}
        {!invLoading && !invError && invites.length === 0 && <EmptyBox text={t("invitations.empty")} />}
        {invites.length > 0 && (
          <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white text-sm">
            {invites.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
                <div className="min-w-0 flex-1 basis-56">
                  <p className="break-all font-medium text-slate-900">{i.email}</p>
                  <p className="text-xs text-slate-500">
                    {t("invitations.sentBy", { name: i.invited_by_name || "—", date: fmtApiDate(i.created_at, lang) })}
                    {i.state === "pending" ? ` · ${t("invitations.expiresOn", { date: fmtApiDate(i.expires_at, lang) })}` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-600">{t(`invitations.roles.${i.role}`)}</span>
                  <OrgBadge tone={i.state === "pending" ? "invited" : i.state} labelKey={`invitations.state.${i.state}`} />
                </div>
                {(i.state === "pending" || i.state === "expired") && (
                  <div className="flex flex-wrap gap-2">
                    <button type="button" className={btn.small} disabled={readOnly} onClick={() => void resend(i)}>{t("invitations.resend")}</button>
                    {i.state === "pending" && (
                      <button type="button" className={btn.smallDanger} disabled={readOnly} onClick={() => { setDialogError(null); setRevoking(i); }}>{t("invitations.revoke")}</button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        <Pager nextCursor={invCursor} loading={invLoading} onMore={() => loadInvites(invCursor)} />
      </section>

      <InviteDialog open={inviting} orgId={org.id} orgName={org.name} onClose={() => setInviting(false)}
        onSent={(_inv, email) => { setInviting(false); toast.success(t("invitations.sent", { email })); void loadInvites(); void reload(); }} />
      <ReasonDialog
        open={!!removing}
        title={t("organizations.members.removeTitle", { name: removing?.display_name || removing?.email || "" })}
        body={t("organizations.members.removeBody", { name: removing?.display_name || removing?.email || "", org: org.name })}
        confirmLabel={t("organizations.members.remove")} danger busy={busy} error={dialogError}
        onConfirm={doRemove} onCancel={() => setRemoving(null)}
      />
      <ConfirmDialog
        open={!!revoking}
        title={t("invitations.revokeTitle")}
        body={t("invitations.revokeBody", { email: revoking?.email || "" })}
        confirmLabel={t("invitations.revoke")} danger busy={busy} error={dialogError}
        onConfirm={() => void doRevoke()} onCancel={() => setRevoking(null)}
      />
    </div>
  );
}
