"use client";

// Phase 9 S3 (PHASE_9_DESIGN 4.5, 8.1): "Invite students" by email from Course → People. Up to 50 addresses per
// request; each student gets a link valid for 14 days and joins after accepting (never enrolled by staff).
import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import {
  EMAIL_RE, STUDENT_INVITE_MAX, createStudentInvitations, splitEmails, type StudentInvitationsOut,
} from "@/lib/lms/invitations";
import type { Lang } from "@/lib/lms/types";
import { Badge, Button, Dialog, Select, Textarea, type BadgeTone } from "@/components/ui";
import { StudentInviteError } from "./InvitationList";

const RESULT_TONE: Record<string, BadgeTone> = {
  invited: "success", already_enrolled: "neutral", invalid_email: "danger", duplicate: "neutral",
};

export function InviteStudentsDialog({
  open, courseId, courseTitle, onClose, onSent,
}: {
  open: boolean;
  courseId: string;
  courseTitle: string;
  onClose: () => void;
  /** Called after a successful request (the invitation list reloads). */
  onSent: (out: StudentInvitationsOut) => void;
}) {
  const { lang, t } = useTranslation();
  const [text, setText] = useState("");
  const [message, setMessage] = useState("");
  const [language, setLanguage] = useState<Lang>(lang as Lang);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [touched, setTouched] = useState(false);
  const [result, setResult] = useState<StudentInvitationsOut | null>(null);

  useEffect(() => {
    if (open) { setText(""); setMessage(""); setLanguage(lang as Lang); setError(null); setTouched(false); setResult(null); }
  }, [open, lang]);

  const emails = useMemo(() => splitEmails(text), [text]);
  const invalid = emails.filter((e) => !EMAIL_RE.test(e));
  const tooMany = emails.length > STUDENT_INVITE_MAX;
  const fieldError = !touched ? undefined
    : emails.length === 0 ? t("studentInvite.dialog.empty")
    : tooMany ? t("studentInvite.dialog.tooMany", { max: STUDENT_INVITE_MAX, extra: emails.length - STUDENT_INVITE_MAX })
    : invalid.length > 0 ? t("studentInvite.dialog.invalid", { list: invalid.slice(0, 5).join(", ") })
    : undefined;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (emails.length === 0 || tooMany || invalid.length > 0) return;
    setBusy(true);
    setError(null);
    try {
      const out = await createStudentInvitations(courseId, { emails, message: message.trim() || undefined, language });
      setResult(out);
      onSent(out);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const formId = "invite-students-form";
  if (result) {
    return (
      <Dialog open={open} title={t("studentInvite.result.title")} onClose={onClose}
        footer={
          <>
            <Button variant="secondary" onClick={() => { setResult(null); setText(""); setTouched(false); }}>{t("studentInvite.result.inviteMore")}</Button>
            <Button onClick={onClose}>{t("studentInvite.result.done")}</Button>
          </>
        }>
        <div className="space-y-4">
          <ul className="flex flex-wrap gap-2 text-sm">
            <li><Badge tone="success">{t("studentInvite.result.invited", { n: result.invited })}</Badge></li>
            {result.already_enrolled > 0 && <li><Badge tone="neutral">{t("studentInvite.result.alreadyEnrolled", { n: result.already_enrolled })}</Badge></li>}
            {result.invalid > 0 && <li><Badge tone="danger">{t("studentInvite.result.invalid", { n: result.invalid })}</Badge></li>}
          </ul>
          {result.invited > 0 && <p className="text-sm text-slate-600">{t("studentInvite.result.hint")}</p>}
          {result.items.some((i) => i.result !== "invited") && (
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
              {result.items.filter((i) => i.result !== "invited").map((i, n) => (
                <li key={`${i.email}-${n}`} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                  <span className="min-w-0 [overflow-wrap:anywhere] text-slate-900">{i.email || "—"}</span>
                  <Badge tone={RESULT_TONE[i.result] ?? "neutral"}>{t(`studentInvite.result.rows.${i.result}`)}</Badge>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} title={t("studentInvite.dialog.title")} onClose={onClose} busy={busy}
      description={t("studentInvite.dialog.body", { course: courseTitle })}
      footer={
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>{t("lms.common.cancel")}</Button>
          <Button type="submit" form={formId} loading={busy}>
            {emails.length > 0 && !tooMany ? t("studentInvite.dialog.sendN", { n: emails.length }) : t("studentInvite.dialog.send")}
          </Button>
        </>
      }>
      <form id={formId} onSubmit={submit} noValidate className="space-y-4">
        <Textarea label={t("studentInvite.dialog.emails")} rows={6} value={text} disabled={busy} required
          autoComplete="off" spellCheck={false} inputMode="email"
          hint={t("studentInvite.dialog.emailsHint", { max: STUDENT_INVITE_MAX })}
          error={fieldError}
          onChange={(e) => setText(e.target.value)} onBlur={() => setTouched(true)} />
        {emails.length > 0 && !fieldError && (
          <p className="text-sm text-slate-600" aria-live="polite">{t("studentInvite.dialog.count", { n: emails.length })}</p>
        )}
        <Textarea label={t("studentInvite.dialog.message")} rows={3} maxLength={500} value={message} disabled={busy}
          optional hint={t("studentInvite.dialog.messageHint")} onChange={(e) => setMessage(e.target.value)} />
        <Select label={t("studentInvite.dialog.language")} value={language} disabled={busy}
          onChange={(e) => setLanguage(e.target.value as Lang)}
          options={[
            { value: "ky", label: t("studentInvite.languages.ky") },
            { value: "ru", label: t("studentInvite.languages.ru") },
            { value: "en", label: t("studentInvite.languages.en") },
          ]} />
        <p className="text-sm text-slate-600">{t("studentInvite.dialog.expiry")}</p>
        <StudentInviteError error={error} />
      </form>
    </Dialog>
  );
}
