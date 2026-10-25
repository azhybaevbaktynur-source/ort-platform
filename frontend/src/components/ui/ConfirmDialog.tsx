"use client";

import React, { useRef } from "react";
import { CircleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { Button } from "./Button";
import { Dialog } from "./Dialog";

export interface ConfirmDialogProps {
  open: boolean;
  /** The question, naming the action ("Delete the course?"). */
  title: string;
  /** The object the action applies to ("Algebra 9A"), shown highlighted. */
  object?: React.ReactNode;
  /** What will happen, in plain words ("Students lose access. This cannot be undone."). Required. */
  effect: React.ReactNode;
  /** Verb label of the confirm button ("Delete course"). */
  confirmLabel: string;
  cancelLabel?: string;
  /** `danger` for destructive actions: red button, focus starts on Cancel. */
  tone?: "primary" | "danger";
  /** Request running: spinner on the confirm button, the dialog cannot be closed. */
  busy?: boolean;
  /** Error from the last try, shown above the buttons (a string or a ready element). */
  error?: React.ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
  /** Extra content (fields) between the effect text and the buttons. */
  children?: React.ReactNode;
  /** Element focused on open; default: the Cancel button. */
  initialFocusRef?: React.RefObject<HTMLElement | null>;
}

/** Confirmation that names the object and the effect (UX_GUIDELINES §4, dangerous actions). */
export function ConfirmDialog({
  open, title, object, effect, confirmLabel, cancelLabel, tone = "primary", busy = false, error, onConfirm, onCancel, children, initialFocusRef,
}: ConfirmDialogProps) {
  const { t } = useTranslation();
  const cancelRef = useRef<HTMLButtonElement>(null);
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      title={title}
      busy={busy}
      size="md"
      role="alertdialog"
      closeOnBackdrop={false}
      initialFocusRef={initialFocusRef ?? cancelRef}
      footer={
        <>
          <Button ref={cancelRef} variant="secondary" disabled={busy} onClick={onCancel}>{cancelLabel ?? t("ui.cancel")}</Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} loading={busy} onClick={onConfirm}>{confirmLabel}</Button>
        </>
      }
    >
      {object && (
        <p className="mb-3 break-words rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 font-semibold text-slate-900">{object}</p>
      )}
      <div className="text-slate-700">{effect}</div>
      {children}
      {error && (
        typeof error === "string" ? (
          <p role="alert" className="mt-4 flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 px-3 py-2.5 text-sm leading-5 text-danger-800">
            <CircleAlert aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </p>
        ) : (
          <div className="mt-4">{error}</div>
        )
      )}
    </Dialog>
  );
}
