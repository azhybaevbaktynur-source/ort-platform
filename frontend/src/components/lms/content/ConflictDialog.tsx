"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { ConfirmDialog } from "@/components/ui";

/** Stale base_version_id (409 version_conflict): offer to reload the latest version. */
export function ConflictDialog({ open, onReload, onClose }: { open: boolean; onReload: () => void; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <ConfirmDialog open={open} title={t("bank.conflict.title")} effect={t("bank.conflict.body")}
      confirmLabel={t("bank.conflict.reload")} onConfirm={onReload} onCancel={onClose} />
  );
}
