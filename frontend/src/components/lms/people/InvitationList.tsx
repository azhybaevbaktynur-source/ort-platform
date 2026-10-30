"use client";

// Phase 9 S3 (PHASE_9_DESIGN 4.5, 8.1): Course → People → Invitations: the course's student invitations with a status
// filter, "Send again" (new link, the old one stops working) and "Revoke".
import React, { useCallback, useState } from "react";
import { UserPlus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  listStudentInvitations, resendStudentInvitation, revokeStudentInvitation, type InvitationOut, type InvitationState,
} from "@/lib/lms/invitations";
import { fmtApiDate } from "@/lib/format";
import { Button, ConfirmDialog, EmptyState, Select, Table, toast, type TableColumn } from "@/components/ui";
import { OrgBadge, OrgError, apiErrorText } from "@/components/lms/org/OrgUi";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";

type T = (key: string, params?: Record<string, string | number>) => string;

const OWN_CODES = new Set(["course_full", "course_not_open", "student_invitations_disabled", "already_enrolled"]);

/** Error text of the student-invitation endpoints: own codes first, then the shared org / lms texts. */
export function studentInviteErrorText(t: T, error: unknown): string {
  const code = (error as { code?: string } | null)?.code;
  if (code && OWN_CODES.has(code)) return t(`studentInvite.errors.${code}`);
  return apiErrorText(t, error);
}

export function StudentInviteError({ error, className = "" }: { error: unknown; className?: string }) {
  const { t } = useTranslation();
  if (!error) return null;
  const code = (error as { code?: string } | null)?.code;
  if (!code || !OWN_CODES.has(code)) return <OrgError error={error} className={className} />;
  return (
    <div role="alert" className={`rounded-xl border border-danger-200 bg-danger-50 px-3.5 py-3 text-sm text-danger-800 ${className}`}>
      {studentInviteErrorText(t, error)}
    </div>
  );
}

export function InvitationList({
  courseId, canManage, reloadKey = 0, onInvite,
}: {
  courseId: string;
  canManage: boolean;
  /** Bump to reload after new invitations were sent. */
  reloadKey?: number;
  onInvite?: () => void;
}) {
  const { lang, t } = useTranslation();
  const [state, setState] = useState<"" | InvitationState>("");
  const fetchPage = useCallback(
    (cursor: string | null) => listStudentInvitations(courseId, { cursor, state: state || undefined }),
    // reloadKey: a new list after the invite dialog sent invitations
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [courseId, state, reloadKey],
  );
  const list = useCursorList(fetchPage);
  const tableState = useTableState(list);
  const [revoking, setRevoking] = useState<InvitationOut | null>(null);
  const [resendingId, setResendingId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);

  const resend = async (i: InvitationOut) => {
    setRowError(null);
    setResendingId(i.id);
    try {
      const out = await resendStudentInvitation(courseId, i.id);
      if (out && !out.email_sent) toast.error(t("invitations.emailNotSent", { email: i.email }));
      else toast.success(t("invitations.resent", { email: i.email }));
      await list.reload();
    } catch (e) {
      setRowError(e);
    } finally {
      setResendingId(null);
    }
  };
  const doRevoke = async () => {
    if (!revoking) return;
    setBusy(true);
    setDialogError(null);
    try {
      await revokeStudentInvitation(courseId, revoking.id);
      toast.success(t("invitations.revoked", { email: revoking.email }));
      setRevoking(null);
      await list.reload();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };

  const columns: TableColumn<InvitationOut>[] = [
    { key: "email", header: t("invitations.dialog.email"), primary: true, className: "sm:min-w-[12rem]",
      cell: (i) => <span className="[overflow-wrap:anywhere]">{i.email}</span> },
    { key: "state", header: t("studentInvite.list.status"),
      cell: (i) => <OrgBadge tone={i.state === "pending" ? "invited" : i.state} labelKey={`invitations.state.${i.state}`} /> },
    { key: "invitedBy", header: t("invitations.invitedByColumn"),
      cell: (i) => <>{i.invited_by_name || "—"}<span className="block text-sm text-slate-600">{fmtApiDate(i.created_at, lang)}</span></> },
    { key: "validUntil", header: t("invitations.validUntilColumn"), nowrap: true,
      cell: (i) => (i.state === "pending" ? fmtApiDate(i.expires_at, lang) : i.state === "accepted" && i.accepted_at ? fmtApiDate(i.accepted_at, lang) : "—") },
    ...(canManage ? [{
      key: "actions", header: "", actions: true, align: "right" as const,
      cell: (i: InvitationOut) => (i.state === "pending" || i.state === "expired") ? (
        <span className="flex w-full flex-wrap gap-2 sm:w-auto sm:flex-col sm:items-end">
          <Button variant="secondary" size="sm" loading={resendingId === i.id} onClick={() => void resend(i)}>{t("invitations.resend")}</Button>
          {i.state === "pending" && (
            <Button variant="secondary" size="sm" onClick={() => { setDialogError(null); setRevoking(i); }}>{t("invitations.revoke")}</Button>
          )}
        </span>
      ) : null,
    }] : []),
  ];

  return (
    <section aria-labelledby="student-invitations-title">
      <h2 id="student-invitations-title" className="sr-only">{t("studentInvite.list.title")}</h2>
      {rowError ? <StudentInviteError error={rowError} className="mb-3" /> : null}
      <Table
        caption={t("studentInvite.list.title")}
        columns={columns}
        rows={list.items}
        rowKey={(i) => i.id}
        {...tableState}
        search={
          <Select id="student-inv-state" label={t("studentInvite.list.status")} value={state} containerClassName="sm:max-w-xs"
            onChange={(e) => setState(e.target.value as "" | InvitationState)}
            options={[
              { value: "", label: t("studentInvite.list.all") },
              { value: "pending", label: t("invitations.state.pending") },
              { value: "accepted", label: t("invitations.state.accepted") },
              { value: "expired", label: t("invitations.state.expired") },
              { value: "revoked", label: t("invitations.state.revoked") },
            ]} />
        }
        empty={
          <EmptyState title={state ? t("studentInvite.list.emptyFilter") : t("studentInvite.list.empty")}
            description={state ? undefined : t("studentInvite.list.emptyHint")}
            action={!state && canManage && onInvite ? (
              <Button variant="secondary" leftIcon={<UserPlus aria-hidden="true" className="h-4 w-4" />} onClick={onInvite}>{t("studentInvite.invite")}</Button>
            ) : undefined} />
        }
      />
      <MoreError list={list} />
      <ConfirmDialog
        open={!!revoking}
        title={t("invitations.revokeTitle")}
        object={revoking?.email}
        effect={t("invitations.revokeBody", { email: revoking?.email || "" })}
        confirmLabel={t("invitations.revoke")} tone="danger" busy={busy}
        error={dialogError ? <StudentInviteError error={dialogError} /> : undefined}
        onConfirm={() => void doRevoke()} onCancel={() => setRevoking(null)}
      />
    </section>
  );
}
