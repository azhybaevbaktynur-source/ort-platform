"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { createOrgInvitation, type InvitationCreatedOut } from "@/lib/lms/invitations";
import { Button, Dialog, Input, Textarea, toast } from "@/components/ui";
import { OrgError } from "./OrgUi";

/** "Invite teacher" (or org admin) by email; the email goes out in the inviter's UI language. */
export function InviteDialog({
  open, orgId, orgName, role = "teacher", onClose, onSent,
}: {
  open: boolean;
  orgId: string;
  orgName: string;
  role?: "teacher" | "org_admin";
  onClose: () => void;
  onSent: (inv: InvitationCreatedOut | null, email: string) => void;
}) {
  const { lang, t } = useTranslation();
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [invalid, setInvalid] = useState(false);

  useEffect(() => { if (open) { setEmail(""); setMessage(""); setError(null); setInvalid(false); } }, [open]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const addr = email.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addr)) { setInvalid(true); return; }
    setBusy(true);
    setError(null);
    try {
      const inv = await createOrgInvitation(orgId, { email: addr, role, message: message.trim() || undefined, language: lang });
      onSent(inv ?? null, addr);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const title = role === "org_admin" ? t("invitations.dialog.titleAdmin") : t("invitations.dialog.title");
  const formId = "invite-form";
  return (
    <Dialog open={open} title={title} onClose={onClose} busy={busy}
      description={t(role === "org_admin" ? "invitations.dialog.bodyAdmin" : "invitations.dialog.body", { org: orgName })}
      footer={
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>{t("lms.common.cancel")}</Button>
          <Button type="submit" form={formId} loading={busy}>{t("invitations.dialog.send")}</Button>
        </>
      }>
      <form id={formId} onSubmit={submit} noValidate className="space-y-4">
        <Input type="email" autoComplete="off" required label={t("invitations.dialog.email")} value={email} disabled={busy}
          error={invalid ? t("invitations.dialog.emailInvalid") : undefined}
          onChange={(e) => { setEmail(e.target.value); setInvalid(false); }} />
        <Textarea label={t("invitations.dialog.message")} rows={3} maxLength={500} value={message} disabled={busy}
          hint={t("invitations.dialog.messageHint")} onChange={(e) => setMessage(e.target.value)} />
        <p className="text-sm text-slate-600">{t("invitations.dialog.expiry")}</p>
        <OrgError error={error} />
      </form>
    </Dialog>
  );
}

/** Toast after an invitation was created: the backend never fails the call when the email could not be sent. */
export function toastInvitationSent(t: (k: string, p?: Record<string, string | number>) => string, inv: { email_sent: boolean } | null, email: string) {
  if (inv && !inv.email_sent) toast.error(t("invitations.emailNotSent", { email }));
  else toast.success(t("invitations.sent", { email }));
}
