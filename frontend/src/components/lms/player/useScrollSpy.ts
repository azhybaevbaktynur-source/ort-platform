"use client";

import { useCallback, useEffect, useRef, type MutableRefObject, type RefObject } from "react";

/**
 * Phase 8b S3 (PHASE_8B_DESIGN 8.1): which item of the scrolling list is "current", from the viewport.
 *
 * One IntersectionObserver (root = the player's scroll container, top margin = the sticky header) keeps the set of
 * items on screen; on its callbacks and on scroll (coalesced per animation frame) the current item is the last one
 * whose top has passed a reading line 30 % down the visible area (the first visible one before that), or the last
 * visible one once the list is scrolled to its end. Programmatic scrolls (palette, arrows) call `suppress()`: the
 * spy stays quiet for at least 400 ms and until the scroll has been idle for 150 ms, and keeps the target as current.
 */
export function useScrollSpy({
  rootRef, itemRefs, enabled, topOffset, itemsKey, onCurrentChange,
}: {
  rootRef: RefObject<HTMLElement | null>;
  /** position -> item element (filled by callback refs) */
  itemRefs: MutableRefObject<Map<number, HTMLElement>>;
  enabled: boolean;
  /** height of the sticky header above the list (px) */
  topOffset: number;
  /** changes whenever the rendered items change (re-observe) */
  itemsKey: string;
  onCurrentChange: (position: number) => void;
}): { suppress: () => void } {
  const visible = useRef<Set<number>>(new Set());
  const frame = useRef<number | null>(null);
  const prog = useRef<{ active: boolean; until: number; timer: ReturnType<typeof setTimeout> | null }>({ active: false, until: 0, timer: null });
  const topRef = useRef(topOffset);
  topRef.current = topOffset;
  const cbRef = useRef(onCurrentChange);
  cbRef.current = onCurrentChange;
  const last = useRef<number | null>(null);

  const compute = useCallback(() => {
    frame.current = null;
    const root = rootRef.current;
    if (!root || prog.current.active) return;
    const rootRect = root.getBoundingClientRect();
    const zoneTop = rootRect.top + topRef.current;
    const line = zoneTop + Math.max(0, rootRect.bottom - zoneTop) * 0.3;
    // Only after a real scroll: a short list that fits the screen keeps its first item current.
    const atEnd = root.scrollTop > 0 && root.scrollTop + root.clientHeight >= root.scrollHeight - 2;
    const entries = Array.from(itemRefs.current.entries()).sort((a, b) => a[0] - b[0]);
    let pick: number | null = null;
    for (const [pos, el] of entries) {
      if (!visible.current.has(pos)) continue;
      const r = el.getBoundingClientRect();
      if (r.bottom <= zoneTop || r.top >= rootRect.bottom) continue;
      if (pick === null || r.top <= line || atEnd) pick = pos;
    }
    if (pick !== null && pick !== last.current) {
      last.current = pick;
      cbRef.current(pick);
    }
  }, [rootRef, itemRefs]);

  const schedule = useCallback(() => {
    if (frame.current === null) frame.current = requestAnimationFrame(compute);
  }, [compute]);

  /** Release the suppression 150 ms after the last scroll event, never before `until`. */
  const release = useCallback(() => {
    const p = prog.current;
    if (p.timer) clearTimeout(p.timer);
    p.timer = setTimeout(() => {
      if (Date.now() >= p.until) p.active = false;
      else release();
    }, Math.max(150, p.until - Date.now()));
  }, []);

  const suppress = useCallback(() => {
    const p = prog.current;
    p.active = true;
    p.until = Date.now() + 400;
    last.current = null;
    release();
  }, [release]);

  useEffect(() => {
    const root = rootRef.current;
    if (!enabled || !root || typeof IntersectionObserver === "undefined") return;
    visible.current = new Set();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          const pos = Number((e.target as HTMLElement).dataset.pos);
          if (e.isIntersecting) visible.current.add(pos);
          else visible.current.delete(pos);
        }
        schedule();
      },
      { root, rootMargin: `-${Math.round(topRef.current)}px 0px 0px 0px`, threshold: [0, 0.25, 0.5, 0.75, 1] },
    );
    for (const el of itemRefs.current.values()) io.observe(el);
    const onScroll = () => {
      if (prog.current.active) release();
      else schedule();
    };
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      io.disconnect();
      root.removeEventListener("scroll", onScroll);
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      frame.current = null;
    };
  }, [enabled, rootRef, itemRefs, itemsKey, topOffset, schedule, release]);

  useEffect(() => () => {
    if (prog.current.timer) clearTimeout(prog.current.timer);
  }, []);

  return { suppress };
}

/** `prefers-reduced-motion: reduce` right now (read at scroll time, so a settings change applies at once). */
export function prefersReducedMotion(): boolean {
  try {
    return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}
