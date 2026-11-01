"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { Button, Dialog } from "@/components/ui";
import { Palette, type PaletteGroup } from "./Palette";

/**
 * The popup of the bottom bar's "Question n of N": question grid, legend and the way to the review page. A real modal
 * (`Dialog`): focus trap, Esc, focus returns to the bar's button. Only the grid scrolls; the footer stays in view.
 */
export function QuestionMap({ open, onClose, groups, currentPosition, description, currentRef, onSelect, onReview }: {
  open: boolean;
  onClose: () => void;
  groups: PaletteGroup[];
  currentPosition: number;
  description: string;
  currentRef: React.RefObject<HTMLButtonElement | null>;
  onSelect: (position: number) => void;
  onReview: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("player.palette.title")}
      description={description}
      initialFocusRef={currentRef}
      className="mb-[calc(4.5rem+env(safe-area-inset-bottom))] mt-auto max-h-[calc(100dvh-6rem)]"
      footer={(
        <Button variant="secondary" fullWidth onClick={onReview} className="border-brand-600 text-brand-700 hover:bg-brand-50 sm:flex-1">
          {t("player.review.open")}
        </Button>
      )}
    >
      <Palette groups={groups} currentPosition={currentPosition} onSelect={onSelect} currentRef={currentRef} />
    </Dialog>
  );
}
