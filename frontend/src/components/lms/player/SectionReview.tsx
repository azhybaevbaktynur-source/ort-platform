"use client";

import React, { useEffect, useId, useRef } from "react";
import { Bookmark } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { Button, cn, focusRing } from "@/components/ui";
import { paletteEntryLabel, type PaletteGroup } from "./Palette";

/**
 * The review page (BLUEBOOK_PLAYER): a view inside the player, not a route. Lists the questions the student can still
 * reach with their state (one section in forward-only mode: closed sections are never offered) and holds the finish
 * button, which opens the unchanged confirmation dialogs.
 */
export function SectionReview({ groups, currentPosition, summary, finishLabel, onJump, onFinish }: {
  groups: PaletteGroup[];
  currentPosition: number;
  summary: string;
  finishLabel: string;
  onJump: (position: number) => void;
  onFinish: () => void;
}) {
  const { t } = useTranslation();
  const headingId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);

  // One task later, so the question map that is closing gives focus back to its button first.
  useEffect(() => {
    const id = setTimeout(() => headingRef.current?.focus({ preventScroll: true }), 0);
    return () => clearTimeout(id);
  }, []);

  return (
    <section aria-labelledby={headingId} className="mx-auto w-full max-w-4xl space-y-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-xs md:p-7">
      <div className="space-y-1">
        <h2 id={headingId} ref={headingRef} tabIndex={-1} className="text-xl font-bold text-slate-900 outline-none">{t("player.review.title")}</h2>
        <p className="text-sm text-slate-700">{summary}</p>
        <p className="text-sm text-slate-600">{t("player.review.hint")}</p>
      </div>
      {groups.map((g) => (
        <div key={g.sectionPos} className="space-y-2">
          {groups.length > 1 && g.title ? <h3 className="text-sm font-semibold text-slate-700">{g.title}</h3> : null}
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-6">
            {g.entries.map((e) => (
              <button
                key={e.position}
                type="button"
                onClick={() => onJump(e.position)}
                aria-current={e.position === currentPosition ? "true" : undefined}
                aria-label={paletteEntryLabel(t, e)}
                className={cn(
                  "relative flex min-h-16 flex-col items-center justify-center rounded-xl border px-1 py-2 text-center transition-colors",
                  focusRing,
                  e.answered
                    ? "border-emerald-400 bg-emerald-50 text-emerald-900 hover:bg-emerald-100"
                    : "border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
                )}
              >
                <span className="text-base font-bold leading-6">{e.label}</span>
                <span className="text-xs leading-4">{e.answered ? t("player.palette.answered") : t("player.palette.unanswered")}</span>
                {e.flagged ? (
                  <Bookmark className="absolute right-1.5 top-1.5 h-3.5 w-3.5 fill-amber-500 text-amber-600" aria-hidden="true" />
                ) : null}
              </button>
            ))}
          </div>
        </div>
      ))}
      <div className="flex justify-end border-t border-slate-100 pt-5">
        <Button onClick={onFinish} className="w-full sm:w-auto">{finishLabel}</Button>
      </div>
    </section>
  );
}
