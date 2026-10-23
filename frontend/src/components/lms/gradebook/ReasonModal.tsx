"use client";

import React, { useEffect, useId, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { Modal } from "@/components/lms/assessments/Modal";
import { SchemeError } from "@/components/lms/grading/schemes/SchemeError";
import { btnPrimary, btnSecondary, inputCls } from "@/components/lms/content/ui";
import { REASON_MAX } from "./gradebookModel";

/** Confirmation with a reason (required unless `optional`); grading errors are translated by SchemeError. */
export function ReasonModal({
  open, title, body, confirmLabel, danger = false, optional = false, busy = false, error, onConfirm, onCancel,
}: {
  open: boolean;
  title: string;
  body?: string;
  confirmLabel: string;
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

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const r = reason.trim();
    if (!optional && !r) { setMissing(true); return; }
    onConfirm(r);
  }

  return (
    <Modal open={open} title={title} onClose={onCancel} busy={busy}>
      <form onSubmit={submit} className="space-y-3">
        {body && <p className="text-sm text-slate-600">{body}</p>}
        <div>
          <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-700">
            {optional ? t("gradebook.reason.optional") : t("gradebook.reason.required")}
          </label>
          <textarea id={id} value={reason} rows={3} maxLength={REASON_MAX} aria-invalid={missing}
            onChange={(e) => { setReason(e.target.value); setMissing(false); }} className={inputCls} />
          {missing && <p role="alert" className="mt-1 text-xs text-red-700">{t("gradebook.reason.missing")}</p>}
        </div>
        <SchemeError error={error} />
        <div className="flex justify-end gap-2">
          <button type="button" disabled={busy} onClick={onCancel} className={btnSecondary}>{t("lms.common.cancel")}</button>
          <button type="submit" disabled={busy}
            className={danger ? "rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50" : btnPrimary}>
            {busy ? t("lms.common.loading") : confirmLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}
