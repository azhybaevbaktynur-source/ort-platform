"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { createOrgInvitation, type InvitationCreatedOut } from "@/lib/lms/invitations";
import { toast } from "@/components/ui/Toast";
import { Modal } from "@/components/lms/assessments/Modal";
import { OrgError, btn, inputCls, labelCls } from "./OrgUi";

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
  return (
    <Modal open={open} title={title} onClose={onClose} busy={busy}>
      <form onSubmit={submit} noValidate className="space-y-4">
        <p className="text-sm text-slate-600">{t(role === "org_admin" ? "invitations.dialog.bodyAdmin" : "invitations.dialog.body", { org: orgName })}</p>
        <div>
          <label htmlFor="inv-email" className={labelCls}>{t("invitations.dialog.email")}</label>
          <input id="inv-email" type="email" autoComplete="off" required value={email} disabled={busy} aria-invalid={invalid}
            onChange={(e) => { setEmail(e.target.value); setInvalid(false); }} className={inputCls} />
          {invalid && <p role="alert" className="mt-1 text-xs text-red-700">{t("invitations.dialog.emailInvalid")}</p>}
        </div>
        <div>
          <label htmlFor="inv-message" className={labelCls}>{t("invitations.dialog.message")}</label>
          <textarea id="inv-message" rows={3} maxLength={500} value={message} disabled={busy}
            onChange={(e) => setMessage(e.target.value)} className={inputCls} />
          <p className="mt-1 text-xs text-slate-500">{t("invitations.dialog.messageHint")}</p>
        </div>
        <p className="text-xs text-slate-500">{t("invitations.dialog.expiry")}</p>
        <OrgError error={error} />
        {/* Phase 6 S8 (UX T1): primary on top on a phone, on the right on desktop. */}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button type="button" className={btn.secondary} disabled={busy} onClick={onClose}>{t("lms.common.cancel")}</button>
          <button type="submit" className={btn.primary} disabled={busy}>{busy ? t("lms.common.loading") : t("invitations.dialog.send")}</button>
        </div>
      </form>
    </Modal>
  );
}

/** Toast after an invitation was created: the backend never fails the call when the email could not be sent. */
export function toastInvitationSent(t: (k: string, p?: Record<string, string | number>) => string, inv: { email_sent: boolean } | null, email: string) {
  if (inv && !inv.email_sent) toast.error(t("invitations.emailNotSent", { email }));
  else toast.success(t("invitations.sent", { email }));
}
