"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button, Dialog } from "@/components/ui";

const noop = () => {};

/**
 * Forward-only warning before closing a section. Phase 6 `Dialog` (S7b, P5): focus trap, Esc, focus returns to
 * the finish button. Red only for the sentence that cannot be undone; the counts stay neutral.
 */
export function SectionEndDialog({ sectionTitle, unanswered, flagged, busy, error, onConfirm, onCancel }: {
  sectionTitle: string;
  unanswered: number;
  flagged: number;
  busy: boolean;
  error?: unknown;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Dialog open onClose={onCancel} busy={busy} closeOnBackdrop={false} title={t("player.sectionEnd.title", { section: sectionTitle })}
      footer={<>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>{t("player.sectionEnd.stay")}</Button>
        <Button onClick={onConfirm} loading={busy}>{t("player.sectionEnd.confirm")}</Button>
      </>}>
      <div className="space-y-3">
        <p className="font-semibold text-danger-700">{t("player.sectionEnd.noReturn")}</p>
        <Counts unanswered={unanswered} flagged={flagged} />
        <ErrorMessage error={error} />
      </div>
    </Dialog>
  );
}

export function SubmitDialog({ unanswered, flagged, busy, error, onConfirm, onCancel }: {
  unanswered: number;
  flagged: number;
  busy: boolean;
  error?: unknown;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Dialog open onClose={onCancel} busy={busy} closeOnBackdrop={false} title={t("player.submit.title")}
      footer={<>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>{t("player.submit.back")}</Button>
        <Button onClick={onConfirm} loading={busy}>{t("player.submit.confirm")}</Button>
      </>}>
      <div className="space-y-3">
        <p className="font-semibold text-danger-700">{t("player.submit.body")}</p>
        <Counts unanswered={unanswered} flagged={flagged} />
        <ErrorMessage error={error} />
      </div>
    </Dialog>
  );
}

function Counts({ unanswered, flagged }: { unanswered: number; flagged: number }) {
  const { t } = useTranslation();
  return (
    <ul className="list-disc space-y-1 pl-5 text-slate-700">
      <li className={unanswered > 0 ? "font-semibold text-slate-900" : ""}>{t("player.counts.unanswered", { n: unanswered })}</li>
      <li className={flagged > 0 ? "font-semibold text-slate-900" : ""}>{t("player.counts.flagged", { n: flagged })}</li>
    </ul>
  );
}

/** Not dismissable: shown while the time-up submit runs. */
export function TimeUpDialog({ error, onRetry }: { error?: unknown; onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <Dialog open onClose={noop} hideCloseButton closeOnBackdrop={false} title={t("player.timeUp.title")}
      footer={error ? <Button onClick={onRetry}>{t("lms.common.retry")}</Button> : undefined}>
      <div className="space-y-3">
        <p>{t("player.timeUp.body")}</p>
        <ErrorMessage error={error} />
      </div>
    </Dialog>
  );
}

/** Attempt or section was closed on the server (deadline passed, closed elsewhere). */
export function ClosedDialog({ finished, onContinue }: { finished: boolean; onContinue: () => void }) {
  const { t } = useTranslation();
  return (
    <Dialog open onClose={noop} hideCloseButton closeOnBackdrop={false} title={finished ? t("player.closed.finishedTitle") : t("player.closed.sectionTitle")}
      footer={<Button onClick={onContinue}>{finished ? t("player.closed.toResult") : t("player.closed.continue")}</Button>}>
      <p>{finished ? t("player.closed.finishedBody") : t("player.closed.sectionBody")}</p>
    </Dialog>
  );
}
