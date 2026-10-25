"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { SchemeError } from "@/components/lms/grading/schemes/SchemeError";
import { ReasonDialog } from "@/components/ui";
import { REASON_MAX } from "./gradebookModel";

/**
 * Confirmation with a reason (required unless `optional`); grading errors are translated by SchemeError.
 * Phase 6b S5c: one consistent dialog: built on the design-system `ReasonDialog` (names the object and the effect,
 * focus trap, Esc). The API is unchanged; `object` is new and optional.
 */
export function ReasonModal({
  open, title, body, object, confirmLabel, danger = false, optional = false, busy = false, error, onConfirm, onCancel,
}: {
  open: boolean;
  title: string;
  body?: string;
  /** What the action applies to (student and attempt), shown highlighted. */
  object?: React.ReactNode;
  confirmLabel: string;
  danger?: boolean;
  optional?: boolean;
  busy?: boolean;
  error?: unknown;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  return (
    <ReasonDialog
      open={open}
      title={title}
      object={object}
      effect={body ?? ""}
      confirmLabel={confirmLabel}
      tone={danger ? "danger" : "primary"}
      optional={optional}
      busy={busy}
      reasonLabel={optional ? t("gradebook.reason.optional") : t("gradebook.reason.required")}
      maxLength={REASON_MAX}
      error={error ? <SchemeError error={error} /> : undefined}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}
