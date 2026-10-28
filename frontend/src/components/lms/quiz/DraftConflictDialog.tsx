"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { Button, Dialog } from "@/components/ui";

/**
 * Card conflicts (PHASE_7C_DESIGN 7):
 * - `draft`: another tab or teacher saved this card's draft meanwhile (409 `draft_conflict` / `draft_exists`):
 *   take their text or keep mine (mine is saved over theirs);
 * - `version`: someone saved a newer version of the question since the card opened (409 `version_conflict`):
 *   keep my draft on top of the new version, or discard my changes.
 */
export function DraftConflictDialog({
  kind, otherName, busy, onPrimary, onSecondary, onClose,
}: {
  kind: "draft" | "version" | null;
  otherName?: string | null;
  busy: boolean;
  /** draft: keep mine; version: keep my draft. */
  onPrimary: () => void;
  /** draft: take theirs; version: discard my changes. */
  onSecondary: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const draft = kind === "draft";
  return (
    <Dialog open={!!kind} onClose={onClose} busy={busy} role="alertdialog"
      title={draft ? t("quizEditor.conflict.title") : t("quizEditor.conflict.versionTitle")}
      description={draft
        ? (otherName ? t("quizEditor.conflict.bodyNamed", { name: otherName }) : t("quizEditor.conflict.body"))
        : t("quizEditor.conflict.versionBody")}
      footer={(
        <>
          <Button variant="secondary" disabled={busy} onClick={onSecondary}>
            {draft ? t("quizEditor.conflict.takeTheirs") : t("quizEditor.conflict.discardMine")}
          </Button>
          <Button variant="primary" loading={busy} onClick={onPrimary}>
            {draft ? t("quizEditor.conflict.keepMine") : t("quizEditor.conflict.keepDraft")}
          </Button>
        </>
      )} />
  );
}
