"use client";

import React from "react";
import { BookOpen, ChevronDown, ChevronUp } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { TemplatePassage } from "@/components/lms/PlainPassage";
import { cn, focusRing } from "@/components/ui";
import type { StudentPassage } from "@/lib/lms/attemptTypes";
import type { PassageDisplay } from "@/lib/lms/blocks";

/**
 * The reading text. Side by side with the question from `xl`; below that it sits above the question and can be
 * folded away with the sticky `PassageToggle` (S7b, P6), open by default. The text itself (line numbers) is the
 * unchanged `TemplatePassage`.
 */
export const PassagePane = React.forwardRef<HTMLElement, {
  passage: StudentPassage; open?: boolean; id?: string; scrollMarginTop?: number;
  /** Phase 8b S3: renderer from the attempt state (`passage_display`); absent = course template. */
  display?: PassageDisplay | null;
}>(
  function PassagePane({ passage, open = true, id, scrollMarginTop, display }, ref) {
    return (
      <section
        ref={ref}
        id={id}
        style={scrollMarginTop ? { scrollMarginTop } : undefined}
        className={cn(
          "rounded-2xl border border-slate-200 bg-white p-3 sm:p-5 shadow-xs xl:block lg:max-h-[calc(100vh-11rem)] lg:overflow-y-auto",
          !open && "hidden",
        )}
      >
        {passage.title ? <h2 className="mb-3 text-base font-bold text-slate-900">{passage.title}</h2> : null}
        {passage.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={passage.image_url} alt="" className="mb-3 max-h-72 w-auto rounded-lg" />
        ) : null}
        <TemplatePassage text={passage.body} display={display} />
      </section>
    );
  },
);

/** Phone / tablet bar that stays under the player header while the text and its questions scroll. */
export function PassageToggle({ passage, open, controls, top, onToggle }: {
  passage: StudentPassage;
  open: boolean;
  controls: string;
  top: number;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-controls={controls}
      style={{ top }}
      className={cn(
        "sticky z-[5] flex min-h-11 w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white/95 px-4 py-2 text-left text-sm shadow-sm backdrop-blur xl:hidden",
        focusRing,
      )}
    >
      <span className="flex min-w-0 items-center gap-2 font-semibold text-slate-900">
        <BookOpen className="h-4 w-4 shrink-0 text-brand-700" aria-hidden="true" />
        <span className="truncate">{passage.title ? t("player.passage.textTitle", { title: passage.title }) : t("player.passage.text")}</span>
      </span>
      <span className="flex shrink-0 items-center gap-1 font-semibold text-brand-700">
        {open ? t("player.passage.hide") : t("player.passage.show")}
        {open ? <ChevronUp className="h-4 w-4" aria-hidden="true" /> : <ChevronDown className="h-4 w-4" aria-hidden="true" />}
      </span>
    </button>
  );
}
