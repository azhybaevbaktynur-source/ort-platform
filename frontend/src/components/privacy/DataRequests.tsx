"use client";

import React, { useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { fmtApiDate } from "@/lib/format";
import { Badge, Button, ConfirmDialog, Input, type BadgeTone } from "@/components/ui";
import { cancelDataRequest, createDataRequest, downloadDataExport, type DataRequestOut, type PrivacyState } from "./privacyApi";
import { PrivacyError } from "./privacyErrors";

export const REQUEST_TONE: Record<DataRequestOut["status"], BadgeTone> = { pending: "warning", completed: "success", rejected: "danger", cancelled: "neutral" };

/** `Download my data`, `Delete account` and the person's own requests. */
export function DataRequests({ state, onChanged }: { state: PrivacyState; onChanged: () => Promise<void> }) {
  const { lang, t } = useTranslation();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [deleting, setDeleting] = useState(false);
  const [password, setPassword] = useState("");
  const [deleteError, setDeleteError] = useState<unknown>(null);

  const download = async () => {
    setBusy("download");
    setError(null);
    try {
      const open = state.requests.find((r) => r.kind === "export" && r.status === "pending");
      const req = open ?? await createDataRequest("export");
      await downloadDataExport(req.id);
      await onChanged();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const requestDelete = async () => {
    setBusy("delete");
    setDeleteError(null);
    try {
      await createDataRequest("delete", password);
      setDeleting(false);
      setPassword("");
      await onChanged();
    } catch (e) {
      setDeleteError(e);
    } finally {
      setBusy(null);
    }
  };

  const cancel = async (id: string) => {
    setBusy(id);
    setError(null);
    try {
      await cancelDataRequest(id);
      await onChanged();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const deleteOpen = state.requests.some((r) => r.kind === "delete" && r.status === "pending");
  return (
    <>
      <PrivacyError error={error} className="mb-3" />
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <Button variant="secondary" loading={busy === "download"} disabled={!!busy} onClick={() => void download()}>{t("privacy.data.download")}</Button>
        {!deleteOpen && (
          <Button variant="dangerOutline" disabled={!!busy} onClick={() => { setDeleteError(null); setPassword(""); setDeleting(true); }}>{t("privacy.data.delete")}</Button>
        )}
      </div>
      {state.requests.length > 0 && (
        <ul aria-label={t("privacy.requests.title")} className="mt-4 divide-y divide-slate-100 border-t border-slate-100">
          {state.requests.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="min-w-0">
                <span className="block break-words text-sm font-medium text-slate-900">{t(`privacy.requests.kind.${r.kind}`)}</span>
                <span className="block text-sm text-slate-600">
                  {fmtApiDate(r.requested_at, lang)}
                  {r.reject_code ? ` · ${t(`privacy.admin.rejectCodes.${r.reject_code}`)}` : ""}
                </span>
              </span>
              <span className="flex flex-wrap items-center gap-2">
                <Badge tone={REQUEST_TONE[r.status]}>{t(`privacy.requests.status.${r.status}`)}</Badge>
                {r.status === "pending" && (
                  <Button variant="secondary" size="sm" loading={busy === r.id} disabled={!!busy} onClick={() => void cancel(r.id)}>{t("privacy.requests.cancel")}</Button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog open={deleting} tone="danger" busy={busy === "delete"}
        title={t("privacy.data.deleteTitle")} effect={t("privacy.data.deleteEffect")} confirmLabel={t("privacy.data.delete")}
        error={deleteError ? <PrivacyError error={deleteError} /> : undefined}
        onConfirm={() => void requestDelete()} onCancel={() => setDeleting(false)}>
        <Input label={t("auth.password")} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </ConfirmDialog>
    </>
  );
}
