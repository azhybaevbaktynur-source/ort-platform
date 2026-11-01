"use client";

import React, { useEffect, useRef } from "react";
import { ChevronDown, MoreHorizontal } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { cn, focusRing } from "@/components/ui";

export type BarPopup = "directions" | "more" | null;

/**
 * The exam player's top bar (BLUEBOOK_PLAYER): section name and "Directions" left, timer center, save status and "More"
 * right. Below `sm` a problem save state (offline, error) takes its own row, so it never squeezes the timer.
 */
export const PlayerTopBar = React.forwardRef<HTMLElement, {
  sectionTitle: string;
  /** "Section n of N" (forward-only); screen readers only on phones, the question map shows it there. */
  sectionOf: string | null;
  instructions: string;
  timer: React.ReactNode;
  save: React.ReactNode;
  saveProblem: boolean;
  popup: BarPopup;
  onPopup: (popup: BarPopup) => void;
}>(function PlayerTopBar({ sectionTitle, sectionOf, instructions, timer, save, saveProblem, popup, onPopup }, ref) {
  const { t } = useTranslation();
  return (
    <header ref={ref} data-testid="player-top-bar" className="sticky top-0 z-20 shrink-0 border-b border-slate-200 bg-white">
      <div className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] items-center gap-x-2 gap-y-1 px-4 py-1.5 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] lg:px-8">
        <div className="min-w-0">
          <p title={sectionTitle} className="line-clamp-2 text-sm font-bold leading-tight text-slate-900 sm:truncate sm:leading-5">{sectionTitle}</p>
          <div className="flex min-h-7 items-center gap-x-3">
            {sectionOf ? <span className="sr-only whitespace-nowrap text-xs text-slate-600 sm:not-sr-only">{sectionOf}</span> : null}
            {instructions ? (
              <BarPopover
                label={t("player.directions")}
                open={popup === "directions"}
                onOpen={() => onPopup("directions")}
                onClose={() => onPopup(null)}
                buttonClassName="relative -ml-1 inline-flex items-center gap-0.5 rounded px-1 text-xs font-semibold text-brand-700 after:absolute after:inset-x-0 after:-inset-y-2 hover:underline"
                buttonContent={<>{t("player.directions")}<ChevronDown className="h-3.5 w-3.5" aria-hidden="true" /></>}
                panelClassName="left-0"
              >
                <p className="mb-1 font-semibold text-slate-900">{t("player.instructions")}</p>
                <p className="whitespace-pre-line">{instructions}</p>
              </BarPopover>
            ) : null}
          </div>
        </div>
        <div className="flex justify-center">{timer}</div>
        <div className="contents min-w-0 sm:flex sm:items-center sm:justify-end sm:gap-2">
          <div className={cn("min-w-0", saveProblem && "max-sm:col-span-4 max-sm:row-start-2")}>{save}</div>
          <div className="max-sm:col-start-4 max-sm:row-start-1">
            <BarPopover
              label={t("player.more")}
              open={popup === "more"}
              onOpen={() => onPopup("more")}
              onClose={() => onPopup(null)}
              buttonClassName="inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white px-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 sm:min-h-9 sm:px-3"
              buttonContent={<>
                <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                <span className="hidden sm:inline">{t("player.more")}</span>
              </>}
              panelClassName="right-0"
            >
              <p>{t("player.shortcuts")}</p>
            </BarPopover>
          </div>
        </div>
      </div>
    </header>
  );
});

/** Text under a bar button. Esc closes it and gives focus back to the button; a click elsewhere closes it. */
function BarPopover({ label, open, onOpen, onClose, buttonClassName, buttonContent, panelClassName, children }: {
  label: string;
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
  buttonClassName: string;
  buttonContent: React.ReactNode;
  panelClassName: string;
  children: React.ReactNode;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      onClose();
      buttonRef.current?.focus();
    };
    const onDown = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [open, onClose]);

  return (
    <div ref={wrapRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-label={label}
        aria-expanded={open}
        onClick={() => (open ? onClose() : onOpen())}
        className={cn(buttonClassName, focusRing)}
      >
        {buttonContent}
      </button>
      {open ? (
        <div
          ref={panelRef}
          tabIndex={-1}
          role="group"
          aria-label={label}
          className={cn(
            "absolute top-full z-30 mt-2 max-h-[60dvh] w-[calc(100vw-2rem)] max-w-md overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-700 shadow-lg outline-none",
            panelClassName,
          )}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}
