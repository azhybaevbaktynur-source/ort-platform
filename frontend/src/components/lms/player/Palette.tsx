"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";

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

/** Navigation grid with answered/flagged markers. Groups are the sections shown (one in forward-only mode). */
export function Palette({
  groups,
  currentPosition,
  onSelect,
}: {
  groups: PaletteGroup[];
  currentPosition: number;
  onSelect: (position: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <nav aria-label={t("player.palette.title")} className="flex flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
      <h3 className="mb-3 text-sm font-bold text-slate-900">{t("player.palette.title")}</h3>
      <div className="max-h-72 space-y-3 overflow-y-auto p-1">
        {groups.map((g) => (
          <div key={g.sectionPos}>
            {groups.length > 1 && g.title ? <p className="mb-1.5 text-xs font-semibold text-slate-500">{g.title}</p> : null}
            <div className="grid grid-cols-5 gap-2">
              {g.entries.map((e) => {
                const cur = e.position === currentPosition;
                let cls = "border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100";
                if (cur) cls = "border-brand-600 bg-brand-600 text-white font-bold ring-2 ring-brand-300";
                else if (e.flagged) cls = "border-amber-400 bg-amber-100 text-amber-900 font-bold";
                else if (e.answered) cls = "border-emerald-400 bg-emerald-50 text-emerald-800 font-semibold";
                return (
                  <button
                    key={e.position}
                    type="button"
                    onClick={() => onSelect(e.position)}
                    aria-current={cur ? "true" : undefined}
                    aria-label={`${t("player.question")} ${e.label}${e.answered ? `, ${t("player.palette.answered")}` : ""}${e.flagged ? `, ${t("player.palette.flagged")}` : ""}`}
                    className={`relative flex h-10 items-center justify-center rounded-xl border text-xs transition-all ${cls}`}
                  >
                    {e.label}
                    {e.flagged && !cur ? <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-amber-500" /> : null}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 border-t border-slate-100 pt-4 text-[11px] text-slate-600">
        <Legend cls="bg-emerald-100 border-emerald-400" text={t("player.palette.answered")} />
        <Legend cls="bg-amber-100 border-amber-400" text={t("player.palette.flagged")} />
        <Legend cls="bg-slate-100 border-slate-200" text={t("player.palette.unanswered")} />
        <Legend cls="bg-brand-600 border-brand-600" text={t("player.palette.current")} />
      </div>
    </nav>
  );
}

function Legend({ cls, text }: { cls: string; text: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`h-3 w-3 rounded-md border ${cls}`} />
      <span>{text}</span>
    </div>
  );
}
