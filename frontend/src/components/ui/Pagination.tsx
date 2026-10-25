"use client";

import React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { Button } from "./Button";
import { cn } from "./utils";

export interface PaginationProps {
  /**
   * Cursor of the next page (`next_cursor` from the API); null/undefined = no more pages.
   * In "load more" mode the button shows while this is set.
   */
  nextCursor?: string | null;
  /** "Load more" mode: append the next page. */
  onLoadMore?: () => void;
  /** Previous/next mode (instead of load more): pass both handlers. */
  onPrevious?: () => void;
  onNext?: () => void;
  hasPrevious?: boolean;
  /** Next page is being loaded. */
  loading?: boolean;
  /** Optional "20 of 124 shown" line. */
  shown?: number;
  total?: number;
  className?: string;
}

/** Cursor pagination: "Load more" (default) or Previous / Next. Hidden when there is nothing to page. */
export function Pagination({ nextCursor, onLoadMore, onPrevious, onNext, hasPrevious = false, loading = false, shown, total, className }: PaginationProps) {
  const { t } = useTranslation();
  const hasNext = !!nextCursor;
  const prevNext = !!onPrevious && !!onNext;
  const countLine = shown !== undefined && total !== undefined ? t("ui.pagination.shown", { shown, total }) : null;
  if (!prevNext && !hasNext && !countLine) return null;
  if (prevNext && !hasNext && !hasPrevious && !countLine) return null;
  return (
    <nav aria-label={t("ui.pagination.label")} className={cn("mt-4 flex flex-col items-center gap-3 sm:flex-row sm:justify-between", className)}>
      <p className="text-sm text-slate-600" aria-live="polite">{countLine}</p>
      {prevNext ? (
        <div className="flex w-full gap-2 sm:w-auto">
          <Button variant="secondary" className="flex-1 sm:flex-none" disabled={!hasPrevious || loading} onClick={onPrevious}
            leftIcon={<ChevronLeft aria-hidden="true" className="h-4 w-4" />}>
            {t("ui.pagination.previous")}
          </Button>
          <Button variant="secondary" className="flex-1 sm:flex-none" disabled={!hasNext} loading={loading} onClick={onNext}
            rightIcon={<ChevronRight aria-hidden="true" className="h-4 w-4" />}>
            {t("ui.pagination.next")}
          </Button>
        </div>
      ) : (
        hasNext && onLoadMore && (
          <Button variant="secondary" className="w-full sm:w-auto" loading={loading} onClick={onLoadMore}>
            {t("ui.pagination.loadMore")}
          </Button>
        )
      )}
    </nav>
  );
}
