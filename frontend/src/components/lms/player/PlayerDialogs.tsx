"use client";

import React, { useEffect, useId, useRef } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { ErrorMessage } from "@/components/lms/ErrorMessage";

function Modal({ title, children, actions, dismissable, onClose }: {
  title: string;
  children: React.ReactNode;
  actions: React.ReactNode;
  dismissable?: boolean;
  onClose?: () => void;
}) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>("button")?.focus();
    if (!dismissable || !onClose) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dismissable, onClose]);
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/50 p-4">
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={id} className="w-full max-w-md space-y-4 rounded-2xl bg-white p-6 shadow-xl">
        <h2 id={id} className="text-lg font-bold text-slate-900">{title}</h2>
        <div className="space-y-2 text-sm text-slate-700">{children}</div>
        <div className="flex flex-wrap justify-end gap-2">{actions}</div>
      </div>
    </div>
  );
}

const btnPrimary = "rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50";
const btnGhost = "rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50";

/** Forward-only warning before closing a section. */
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
    <Modal title={t("player.sectionEnd.title", { section: sectionTitle })} dismissable={!busy} onClose={onCancel}
      actions={<>
        <button type="button" className={btnGhost} onClick={onCancel} disabled={busy}>{t("player.sectionEnd.stay")}</button>
        <button type="button" className={btnPrimary} onClick={onConfirm} disabled={busy}>{busy ? t("player.working") : t("player.sectionEnd.confirm")}</button>
      </>}>
      <p className="font-medium text-red-700">{t("player.sectionEnd.noReturn")}</p>
      <Counts unanswered={unanswered} flagged={flagged} />
      <ErrorMessage error={error} />
    </Modal>
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
    <Modal title={t("player.submit.title")} dismissable={!busy} onClose={onCancel}
      actions={<>
        <button type="button" className={btnGhost} onClick={onCancel} disabled={busy}>{t("player.submit.back")}</button>
        <button type="button" className={btnPrimary} onClick={onConfirm} disabled={busy}>{busy ? t("player.working") : t("player.submit.confirm")}</button>
      </>}>
      <p>{t("player.submit.body")}</p>
      <Counts unanswered={unanswered} flagged={flagged} />
      <ErrorMessage error={error} />
    </Modal>
  );
}

function Counts({ unanswered, flagged }: { unanswered: number; flagged: number }) {
  const { t } = useTranslation();
  return (
    <ul className="list-disc space-y-0.5 pl-5">
      <li className={unanswered > 0 ? "font-medium text-amber-700" : ""}>{t("player.counts.unanswered", { n: unanswered })}</li>
      <li className={flagged > 0 ? "font-medium text-amber-700" : ""}>{t("player.counts.flagged", { n: flagged })}</li>
    </ul>
  );
}

/** Not dismissable: shown while the time-up submit runs. */
export function TimeUpDialog({ error, onRetry }: { error?: unknown; onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <Modal title={t("player.timeUp.title")}
      actions={error ? <button type="button" className={btnPrimary} onClick={onRetry}>{t("lms.common.retry")}</button> : null}>
      <p>{t("player.timeUp.body")}</p>
      <ErrorMessage error={error} />
    </Modal>
  );
}

/** Attempt or section was closed on the server (deadline passed, closed elsewhere). */
export function ClosedDialog({ finished, onContinue }: { finished: boolean; onContinue: () => void }) {
  const { t } = useTranslation();
  return (
    <Modal title={finished ? t("player.closed.finishedTitle") : t("player.closed.sectionTitle")}
      actions={<button type="button" className={btnPrimary} onClick={onContinue}>{finished ? t("player.closed.toResult") : t("player.closed.continue")}</button>}>
      <p>{finished ? t("player.closed.finishedBody") : t("player.closed.sectionBody")}</p>
    </Modal>
  );
}
