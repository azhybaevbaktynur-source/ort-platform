"use client";

import React, { useEffect, useMemo, useRef, type RefObject } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { Button, cn } from "@/components/ui";
import type { AttemptContent, AttemptItemState, AttemptState, StudentPassage } from "@/lib/lms/attemptTypes";
import type { PassageDisplay } from "@/lib/lms/blocks";
import { ItemView } from "./ItemView";
import { PassagePane } from "./PassagePane";
import { itemPassage, itemQuestion, type ResponseObj } from "./playerUtils";
import { prefersReducedMotion, useScrollSpy } from "./useScrollSpy";

/** Items mounted at once (PHASE_8B_DESIGN 8.1, P8B-5, owner question Q3). */
export const SCROLL_WINDOW = 30;

type LocalAnswer = { response: ResponseObj; flagged: boolean };

/** A programmatic scroll to an item: `n` grows with every request, so the same position can be asked again. */
export interface ScrollRequest { pos: number; n: number }

/**
 * Phase 8b S3 (PHASE_8B_DESIGN 8.1): the question area of the scrolling display mode. One section at a time, in
 * windows of `SCROLL_WINDOW` items; each item is a focusable landmark (`section#item-<pos>`) with the unchanged
 * `ItemView`; a passage is shown once above the first question of its group (always open). The current item follows
 * the viewport (`useScrollSpy`); the palette, the arrow keys and Prev/Next call `onNavigate`, which scrolls here
 * (`scrollRequest`) and focuses the item. The window footer's actions are visible buttons. State, autosave, timers
 * and dialogs stay in `PlayerShell`.
 */
export function ScrollingItems({
  state, content, visibleItems, currentPos, answers, onAnswer, onToggleFlag, onCurrentChange, onNavigate,
  scrollRequest, scrollRootRef, headerHeight, stickyTop, passageDisplay, instructions, sectionTitle,
  forwardOnly, finishLabel, onFinish,
}: {
  state: AttemptState;
  content: AttemptContent;
  /** The palette's items (forward-only: the current section; free navigation: all). */
  visibleItems: AttemptItemState[];
  currentPos: number;
  answers: Record<number, LocalAnswer>;
  onAnswer: (position: number, response: ResponseObj) => void;
  onToggleFlag: (position: number) => void;
  onCurrentChange: (position: number) => void;
  onNavigate: (position: number) => void;
  scrollRequest: ScrollRequest | null;
  scrollRootRef: RefObject<HTMLElement | null>;
  headerHeight: number;
  stickyTop: number;
  passageDisplay: PassageDisplay | null;
  instructions: string;
  sectionTitle: (pos: number) => string;
  forwardOnly: boolean;
  finishLabel: string;
  onFinish: () => void;
}) {
  const { t } = useTranslation();
  const itemRefs = useRef<Map<number, HTMLElement>>(new Map());

  // ---- the section and window that contain the current item ----
  const curItem = visibleItems.find((i) => i.position === currentPos) ?? visibleItems[0];
  const sectionPos = curItem?.section_pos ?? state.current_section_pos;
  const sectionItems = useMemo(() => visibleItems.filter((i) => i.section_pos === sectionPos), [visibleItems, sectionPos]);
  const idxInSection = Math.max(0, sectionItems.findIndex((i) => i.position === curItem?.position));
  const windowStart = Math.floor(idxInSection / SCROLL_WINDOW) * SCROLL_WINDOW;
  const windowItems = useMemo(() => sectionItems.slice(windowStart, windowStart + SCROLL_WINDOW), [sectionItems, windowStart]);
  const windowEnd = windowStart + windowItems.length;
  const numberOf = useMemo(() => new Map(visibleItems.map((it, i) => [it.position, i + 1])), [visibleItems]);
  const sectionOrder = useMemo(() => Array.from(new Set(visibleItems.map((i) => i.section_pos))), [visibleItems]);
  const sIdx = sectionOrder.indexOf(sectionPos);
  const prevSection = !forwardOnly && sIdx > 0 ? sectionOrder[sIdx - 1] : null;
  const nextSection = !forwardOnly && sIdx >= 0 && sIdx < sectionOrder.length - 1 ? sectionOrder[sIdx + 1] : null;
  const firstOf = (sec: number) => visibleItems.find((i) => i.section_pos === sec)?.position;
  const hasPrevWindow = windowStart > 0;
  const hasNextWindow = windowEnd < sectionItems.length;
  const remaining = sectionItems.length - windowEnd;

  const itemsKey = windowItems.map((i) => i.position).join(",");
  const spy = useScrollSpy({
    rootRef: scrollRootRef, itemRefs, enabled: true, topOffset: headerHeight, itemsKey, onCurrentChange,
  });

  // A section starts at its top (first load, section close, timer, "Next section"; the list remounts after a
  // forward-only section's content loads, so this also runs on mount).
  useEffect(() => {
    const root = scrollRootRef.current;
    if (root && root.scrollTop > 0) {
      spy.suppress();
      root.scrollTo({ top: 0 });
    }
  }, [sectionPos]); // eslint-disable-line react-hooks/exhaustive-deps

  // Palette / arrows / window buttons: scroll the item under the header, then focus it (never on viewport changes).
  // One task later, so a palette sheet that is closing gives focus back to its button first and the item keeps it.
  useEffect(() => {
    if (!scrollRequest) return;
    const id = setTimeout(() => {
      const el = itemRefs.current.get(scrollRequest.pos);
      if (!el) return;
      spy.suppress();
      // The first question of a passage group: show the text above it first (reading order); focus stays on the item.
      const passage = document.querySelector<HTMLElement>(`[data-passage-for="${scrollRequest.pos}"]`);
      (passage ?? el).scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
      el.focus({ preventScroll: true });
    }, 0);
    return () => clearTimeout(id);
  }, [scrollRequest]); // eslint-disable-line react-hooks/exhaustive-deps

  const blocks: React.ReactNode[] = [];
  let lastPassage: string | null = null;
  for (const it of windowItems) {
    const q = itemQuestion(state, content, it);
    const passage: StudentPassage | null = itemPassage(content, it, q);
    if (passage && passage.id !== lastPassage) {
      blocks.push(
        <div key={`p-${passage.id}-${it.position}`} data-passage-for={it.position} style={{ scrollMarginTop: stickyTop }}>
          <PassagePane id={`passage-${passage.id}-${it.position}`} passage={passage} open display={passageDisplay} />
        </div>,
      );
    }
    lastPassage = passage?.id ?? null;
    const cur = it.position === curItem?.position;
    blocks.push(
      <section
        key={it.position}
        id={`item-${it.position}`}
        data-pos={it.position}
        ref={(el) => {
          if (el) itemRefs.current.set(it.position, el);
          else itemRefs.current.delete(it.position);
        }}
        aria-labelledby={`item-${it.position}-h`}
        aria-current={cur ? "true" : undefined}
        tabIndex={-1}
        style={{ scrollMarginTop: stickyTop }}
        className={cn(
          "rounded-2xl outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2",
          cur && "ring-1 ring-brand-300 ring-offset-2 ring-offset-slate-50",
        )}
      >
        {q ? (
          <ItemView
            headingId={`item-${it.position}-h`}
            question={q}
            choiceOrder={it.choice_order}
            number={numberOf.get(it.position) ?? 0}
            total={visibleItems.length}
            response={answers[it.position]?.response ?? null}
            flagged={!!answers[it.position]?.flagged}
            onChange={(r) => onAnswer(it.position, r)}
            onToggleFlag={() => onToggleFlag(it.position)}
          />
        ) : (
          <p id={`item-${it.position}-h`} className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">{t("player.noQuestion")}</p>
        )}
      </section>,
    );
  }

  const lastWindow = !hasNextWindow;
  return (
    <div className="space-y-4" role="region" aria-label={sectionTitle(sectionPos)}>
      {instructions ? (
        <details key={sectionPos} className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700" open>
          <summary className="cursor-pointer py-1 font-semibold text-slate-800">{t("player.instructions")}</summary>
          <p className="mt-2 whitespace-pre-line">{instructions}</p>
        </details>
      ) : null}

      {hasPrevWindow ? (
        <Button variant="secondary" fullWidth onClick={() => onNavigate(sectionItems[windowStart - SCROLL_WINDOW].position)}
          leftIcon={<ChevronUp className="h-4 w-4" aria-hidden="true" />}>
          {t("player.scrolling.showPrevious", { n: SCROLL_WINDOW })}
        </Button>
      ) : prevSection !== null ? (
        <Button variant="secondary" fullWidth onClick={() => { const p = firstOf(prevSection); if (p !== undefined) onNavigate(p); }}
          leftIcon={<ChevronLeft className="h-4 w-4" aria-hidden="true" />}>
          {t("player.scrolling.previousSection")}
        </Button>
      ) : null}

      {blocks.length > 0 ? blocks : <p className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">{t("player.noQuestion")}</p>}

      {/* The window footer: where the list is, and the visible way on (UX section 4: no hidden features). */}
      <div className="sticky bottom-0 z-[5] -mx-4 border-t border-slate-200 bg-white px-4 py-3 sm:mx-0 sm:rounded-2xl sm:border">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <p className="text-sm text-slate-700" aria-live="polite">
            {t("player.scrolling.windowOf", { from: windowStart + 1, to: windowEnd, total: sectionItems.length })}
          </p>
          <div className="flex flex-1 flex-wrap items-center justify-end gap-2">
            {hasNextWindow ? (
              <Button className="sm:min-h-10" onClick={() => onNavigate(sectionItems[windowEnd].position)}
                rightIcon={<ChevronDown className="h-4 w-4" aria-hidden="true" />}>
                {t("player.scrolling.showNext", { n: Math.min(SCROLL_WINDOW, remaining) })}
              </Button>
            ) : nextSection !== null ? (
              <Button className="sm:min-h-10" onClick={() => { const p = firstOf(nextSection); if (p !== undefined) onNavigate(p); }}
                rightIcon={<ChevronRight className="h-4 w-4" aria-hidden="true" />}>
                {t("player.scrolling.nextSection")}
              </Button>
            ) : lastWindow ? (
              <Button className="sm:min-h-10" onClick={onFinish}>{finishLabel}</Button>
            ) : null}
          </div>
        </div>
      </div>
      <p className="hidden text-xs text-slate-500 lg:block">{t("player.shortcuts")}</p>
    </div>
  );
}
