"use client";

import React, { useEffect, useId, useRef } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { ErrorMessage } from "./ErrorMessage";

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  danger = false,
  busy = false,
  error,
  onConfirm,
  onCancel,
  children,
  stackedFooter = false,
}: {
  open: boolean;
  title: string;
  body?: string;
  confirmLabel?: string;
  danger?: boolean;
  busy?: boolean;
  error?: unknown;
  onConfirm: () => void;
  onCancel: () => void;
  children?: React.ReactNode;
  /** Phase 6 S8 (UX T1): opt-in; on a phone the buttons stack full width with the primary on top. */
  stackedFooter?: boolean;
}) {
  const { t } = useTranslation();
  const titleId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h2 id={titleId} className="text-lg font-bold text-slate-900">{title}</h2>
        {body && <p className="mt-2 text-sm text-slate-600">{body}</p>}
        {children}
        {error ? <ErrorMessage error={error} className="mt-3" /> : null}
        <div className={stackedFooter ? "mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end [&>button]:min-h-[44px]" : "mt-5 flex justify-end gap-2"}>
          <button ref={cancelRef} type="button" disabled={busy} onClick={onCancel}
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">
            {t("lms.common.cancel")}
          </button>
          <button type="button" disabled={busy} onClick={onConfirm}
            className={`rounded-xl px-4 py-2 text-sm font-semibold text-white disabled:opacity-50 ${danger ? "bg-red-600 hover:bg-red-700" : "bg-brand-600 hover:bg-brand-700"}`}>
            {busy ? t("lms.common.loading") : confirmLabel || t("lms.common.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
