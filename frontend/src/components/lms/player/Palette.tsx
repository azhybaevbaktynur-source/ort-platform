"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { cn, focusRing } from "@/components/ui";

export interface PaletteEntry {
  position: number;
  /** 1-based number shown on the button (within the section in forward-only mode) */
  label: number;
  answered: boolean;
  flagged: boolean;
  sectionPos: number;
}

export interface PaletteGroup {
  sectionPos: number;
  title: string | null;
  entries: PaletteEntry[];
}

/**
 * Navigation grid. The states add up instead of hiding each other (S7b, P2): the fill says answered (green) or
 * not (grey), a ring marks the question on screen, an amber dot marks a flag (shown on the current question too).
 * Groups are the sections shown (one in forward-only mode). Lives in the question map popup, whose title it shares.
 */
export function Palette({
  groups,
  currentPosition,
  onSelect,
  currentRef,
}: {
  groups: PaletteGroup[];
  currentPosition: number;
  onSelect: (position: number) => void;
  /** Receives the current question's button (initial focus of the popup). */
  currentRef?: React.Ref<HTMLButtonElement>;
}) {
  const { t } = useTranslation();
  return (
    <nav aria-label={t("player.palette.title")} className="flex flex-col">
      <div className="space-y-3 p-1">
        {groups.map((g) => (
          <div key={g.sectionPos}>
            {groups.length > 1 && g.title ? <p className="mb-1.5 text-xs font-semibold text-slate-600">{g.title}</p> : null}
            <div className="grid grid-cols-5 gap-2">
              {g.entries.map((e) => {
                const cur = e.position === currentPosition;
                return (
                  <button
                    key={e.position}
                    ref={cur ? currentRef : undefined}
                    type="button"
                    onClick={() => onSelect(e.position)}
                    aria-current={cur ? "true" : undefined}
                    aria-label={paletteEntryLabel(t, e)}
                    className={cn(
                      "relative flex h-11 items-center justify-center rounded-xl border text-sm transition-colors",
                      focusRing,
                      e.answered
                        ? "border-emerald-400 bg-emerald-100 font-semibold text-emerald-900 hover:bg-emerald-200"
                        : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
                      cur && "font-bold ring-2 ring-brand-600 ring-offset-2",
                    )}
                  >
                    {e.label}
                    {e.flagged ? (
                      <span aria-hidden="true" className="absolute right-1 top-1 h-2.5 w-2.5 rounded-full border border-white bg-amber-500" />
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 border-t border-slate-100 pt-4 text-xs text-slate-600">
        <Legend swatch={<span className="h-3.5 w-3.5 rounded-[5px] border border-slate-300 bg-white ring-2 ring-brand-600 ring-offset-1" />} text={t("player.palette.current")} />
        <Legend swatch={<span className="h-3.5 w-3.5 rounded-[5px] border border-slate-300 bg-white" />} text={t("player.palette.unanswered")} />
        <Legend
          swatch={(
            <span className="relative h-3.5 w-3.5 rounded-[5px] border border-slate-300 bg-white">
              <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full border border-white bg-amber-500" />
            </span>
          )}
          text={t("player.palette.flagged")}
        />
      </div>
    </nav>
  );
}

/** The accessible name of a question's button: its number and its state (grid and review page). */
export function paletteEntryLabel(t: (key: string) => string, e: PaletteEntry): string {
  return `${t("player.question")} ${e.label}${e.answered ? `, ${t("player.palette.answered")}` : ""}${e.flagged ? `, ${t("player.palette.flagged")}` : ""}`;
}

function Legend({ swatch, text }: { swatch: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-2">
      <span aria-hidden="true" className="flex shrink-0">{swatch}</span>
      <span>{text}</span>
    </div>
  );
}
