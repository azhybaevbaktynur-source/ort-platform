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
 * Groups are the sections shown (one in forward-only mode).
 */
export function Palette({
  groups,
  currentPosition,
  onSelect,
  hideTitle,
  currentRef,
}: {
  groups: PaletteGroup[];
  currentPosition: number;
  onSelect: (position: number) => void;
  /** The phone sheet shows the title in its own header. */
  hideTitle?: boolean;
  /** Receives the current question's button (initial focus of the phone sheet). */
  currentRef?: React.Ref<HTMLButtonElement>;
}) {
  const { t } = useTranslation();
  return (
    <nav aria-label={t("player.palette.title")} className={cn("flex flex-col", !hideTitle && "rounded-2xl border border-slate-200 bg-white p-4 shadow-xs")}>
      {!hideTitle && <h3 className="mb-3 text-sm font-bold text-slate-900">{t("player.palette.title")}</h3>}
      <div className={cn("space-y-3 p-1", !hideTitle && "max-h-72 overflow-y-auto")}>
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
                    aria-label={`${t("player.question")} ${e.label}${e.answered ? `, ${t("player.palette.answered")}` : ""}${e.flagged ? `, ${t("player.palette.flagged")}` : ""}`}
                    className={cn(
                      "relative flex h-11 items-center justify-center rounded-xl border text-sm transition-colors lg:h-10",
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
      <div className="mt-4 grid grid-cols-2 gap-2 border-t border-slate-100 pt-4 text-xs text-slate-600">
        <Legend swatch={<span className="h-3.5 w-3.5 rounded-[5px] border border-emerald-400 bg-emerald-100" />} text={t("player.palette.answered")} />
        <Legend swatch={<span className="h-3.5 w-3.5 rounded-[5px] border border-slate-300 bg-white" />} text={t("player.palette.unanswered")} />
        <Legend swatch={<span className="h-3.5 w-3.5 rounded-[5px] border border-slate-300 bg-white ring-2 ring-brand-600 ring-offset-1" />} text={t("player.palette.current")} />
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

function Legend({ swatch, text }: { swatch: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-2">
      <span aria-hidden="true" className="flex shrink-0">{swatch}</span>
      <span>{text}</span>
    </div>
  );
}
