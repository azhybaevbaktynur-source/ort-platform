"use client";

import React, { useEffect, useId, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { ConfirmDialog } from "../ConfirmDialog";

/** Confirm dialog with a reason textarea (required unless `optional`). */
export function ReasonDialog({
  open, title, body, confirmLabel, danger, optional = false, busy, error, onConfirm, onCancel,
}: {
  open: boolean;
  title: string;
  body?: string;
  confirmLabel?: string;
  danger?: boolean;
  optional?: boolean;
  busy?: boolean;
  error?: unknown;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [reason, setReason] = useState("");
  const [missing, setMissing] = useState(false);
  useEffect(() => { if (open) { setReason(""); setMissing(false); } }, [open]);
  const trimmed = reason.trim();
  return (
    <ConfirmDialog
      open={open} title={title} body={body} confirmLabel={confirmLabel} danger={danger} busy={busy}
      error={error} onCancel={onCancel} onConfirm={() => { if (!optional && !trimmed) { setMissing(true); return; } onConfirm(trimmed); }}
    >
      <label htmlFor={id} className="mt-4 block text-sm font-medium text-slate-700">
        {optional ? t("platformAdmin.reasonOptional") : t("platformAdmin.reasonRequired")}
      </label>
      <textarea id={id} value={reason} maxLength={500} rows={3} aria-invalid={missing} onChange={(e) => { setReason(e.target.value); setMissing(false); }}
        className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" />
      {missing && <p role="alert" className="mt-1 text-xs text-red-700">{t("platformAdmin.reasonMissing")}</p>}
    </ConfirmDialog>
  );
}
