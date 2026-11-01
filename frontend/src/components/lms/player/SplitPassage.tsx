"use client";

import React, { useEffect, useRef, useState } from "react";
import { GripVertical } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { focusRing } from "@/components/ui";

const STORAGE_KEY = "ort_player_split";
const MIN = 30;
const MAX = 70;
const STEP = 2;

const clamp = (v: number) => Math.min(MAX, Math.max(MIN, v));

function storedPct(): number {
  try {
    const v = Number(window.sessionStorage.getItem(STORAGE_KEY));
    return Number.isFinite(v) && v > 0 ? clamp(v) : 50;
  } catch {
    return 50;
  }
}

/**
 * Reading (BLUEBOOK_PLAYER): from `lg` the text and the question side by side, each scrolling on its own, with a
 * draggable divider (arrow keys work, 30-70 %, remembered per tab). Below `lg` they stack and the page scrolls.
 */
export function SplitPassage({ passage, questionRef, questionStyle, children }: {
  passage: React.ReactNode;
  questionRef: React.RefObject<HTMLDivElement | null>;
  questionStyle?: React.CSSProperties;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const rootRef = useRef<HTMLDivElement>(null);
  const [pct, setPct] = useState<number>(() => (typeof window === "undefined" ? 50 : storedPct()));

  useEffect(() => {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, String(pct));
    } catch { /* storage unavailable: the position just is not remembered */ }
  }, [pct]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    const next = e.key === "ArrowLeft" ? pct - STEP : e.key === "ArrowRight" ? pct + STEP : e.key === "Home" ? MIN : e.key === "End" ? MAX : null;
    if (next === null) return;
    // These arrows move the divider: the player's question hotkeys must not see them.
    e.preventDefault();
    e.stopPropagation();
    setPct(clamp(next));
  };

  const dragTo = (clientX: number) => {
    const rect = rootRef.current?.getBoundingClientRect();
    if (rect && rect.width > 0) setPct(clamp(Math.round(((clientX - rect.left) / rect.width) * 100)));
  };

  return (
    <div
      ref={rootRef}
      style={{ "--split": `${pct}%` } as React.CSSProperties}
      className="grid grid-cols-1 gap-4 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,var(--split))_0.75rem_minmax(0,1fr)] lg:grid-rows-[minmax(0,1fr)] lg:gap-0"
    >
      {passage}
      <div
        role="separator"
        tabIndex={0}
        aria-orientation="vertical"
        aria-label={t("player.passage.resize")}
        aria-valuemin={MIN}
        aria-valuemax={MAX}
        aria-valuenow={pct}
        onKeyDown={onKeyDown}
        onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); e.preventDefault(); e.currentTarget.focus(); }}
        onPointerMove={(e) => { if (e.currentTarget.hasPointerCapture(e.pointerId)) dragTo(e.clientX); }}
        className={`hidden cursor-col-resize touch-none items-center justify-center border-x border-slate-200 bg-slate-100 text-slate-500 hover:bg-slate-200 lg:flex ${focusRing}`}
      >
        <GripVertical className="h-4 w-4" aria-hidden="true" />
      </div>
      <div ref={questionRef} tabIndex={-1} style={questionStyle} className="min-w-0 space-y-4 outline-none lg:overflow-y-auto lg:p-6">
        {children}
      </div>
    </div>
  );
}
