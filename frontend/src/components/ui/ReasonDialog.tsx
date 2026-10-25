"use client";

import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { ConfirmDialog, type ConfirmDialogProps } from "./ConfirmDialog";
import { Textarea } from "./Textarea";

export interface ReasonDialogProps extends Omit<ConfirmDialogProps, "onConfirm" | "children" | "initialFocusRef"> {
  /** Called with the trimmed reason (may be "" when `optional`). */
  onConfirm: (reason: string) => void;
  /** Reason may be left empty. */
  optional?: boolean;
  /** Label of the reason field; defaults to "Reason (required)" / "Reason (optional)". */
  reasonLabel?: string;
  reasonHint?: string;
  maxLength?: number;
}

/** ConfirmDialog with a reason text field (required unless `optional`); the reason resets on open. */
export function ReasonDialog({ open, onConfirm, optional = false, reasonLabel, reasonHint, maxLength = 500, ...rest }: ReasonDialogProps) {
  const { t } = useTranslation();
  const [reason, setReason] = useState("");
  const [missing, setMissing] = useState(false);
  const fieldRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (open) { setReason(""); setMissing(false); } }, [open]);
  const trimmed = reason.trim();
  return (
    <ConfirmDialog
      {...rest}
      open={open}
      initialFocusRef={fieldRef}
      onConfirm={() => {
        if (!optional && !trimmed) { setMissing(true); fieldRef.current?.focus(); return; }
        onConfirm(trimmed);
      }}
    >
      <Textarea
        ref={fieldRef}
        containerClassName="mt-4"
        label={reasonLabel ?? (optional ? t("ui.reason.optional") : t("ui.reason.required"))}
        hint={reasonHint ?? t("ui.reason.limit", { n: maxLength })}
        error={missing ? t("ui.reason.missing") : undefined}
        value={reason}
        maxLength={maxLength}
        rows={3}
        required={!optional}
        disabled={rest.busy}
        onChange={(e) => { setReason(e.target.value); setMissing(false); }}
      />
    </ConfirmDialog>
  );
}
