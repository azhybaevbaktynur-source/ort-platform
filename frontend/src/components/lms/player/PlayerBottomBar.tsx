"use client";

import React from "react";
import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { Button, cn, focusRing } from "@/components/ui";

/**
 * The exam player's bottom bar (BLUEBOOK_PLAYER): "Back", "Question n of N" (opens the question map), "Next". It stays
 * in the page's flow and sticks to the bottom, so content never sits under it. `BOTTOM_BAR_OFFSET` is its height.
 */
export const BOTTOM_BAR_OFFSET = "bottom-[calc(4rem+env(safe-area-inset-bottom))]";

export const PlayerBottomBar = React.forwardRef<HTMLButtonElement, {
  /** null: no "Back" here (the first question). */
  onBack: (() => void) | null;
  /** null: no "Next" here (the review page has its own finish button). */
  onNext: (() => void) | null;
  n: number;
  total: number;
  mapOpen: boolean;
  anyFlagged: boolean;
  onOpenMap: () => void;
}>(function PlayerBottomBar({ onBack, onNext, n, total, mapOpen, anyFlagged, onOpenMap }, ref) {
  const { t } = useTranslation();
  return (
    <div data-testid="player-bottom-bar" className="sticky bottom-0 z-20 shrink-0 border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)]">
      <div className="grid h-16 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 px-4 lg:px-8">
        <div className="flex justify-start">
          {onBack ? (
            <Button variant="secondary" onClick={onBack} className="px-3 sm:min-h-10 sm:px-4" leftIcon={<ChevronLeft className="hidden h-4 w-4 sm:block" aria-hidden="true" />}>
              {t("player.prev")}
            </Button>
          ) : null}
        </div>
        <button
          ref={ref}
          type="button"
          onClick={onOpenMap}
          aria-haspopup="dialog"
          aria-expanded={mapOpen}
          aria-label={t("player.palette.openLabel", { n, total })}
          className={cn(
            "relative inline-flex min-h-11 items-center gap-1 whitespace-nowrap rounded-xl bg-slate-900 px-3 text-sm font-semibold text-white hover:bg-slate-800 sm:px-4",
            focusRing,
          )}
        >
          {t("player.questionOf", { n, total })}
          <ChevronDown className="h-4 w-4" aria-hidden="true" />
          {anyFlagged ? (
            <span aria-hidden="true" className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full border border-white bg-amber-500" />
          ) : null}
        </button>
        <div className="flex justify-end">
          {onNext ? (
            <Button onClick={onNext} className="px-3 sm:min-h-10 sm:px-4" rightIcon={<ChevronRight className="hidden h-4 w-4 sm:block" aria-hidden="true" />}>
              {t("player.next")}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
});
