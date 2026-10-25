"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { PaginationProps } from "@/components/ui";
import { LoadError, OrgError } from "@/components/lms/org/OrgUi";
import type { useCursorList } from "./useCursorList";

type CursorList<T> = ReturnType<typeof useCursorList<T>>;

/**
 * Table props for a cursor list: skeleton on the first load, a full `ErrorState` when nothing could be
 * loaded, "Load more" pagination, and the "Shown: n" count line.
 */
export function useTableState<T>(list: CursorList<T>, shownCount?: number) {
  const { t } = useTranslation();
  const n = shownCount ?? list.items.length;
  return {
    loading: list.loading,
    error: list.error && list.items.length === 0 ? <LoadError error={list.error} onRetry={() => void list.reload()} /> : undefined,
    pagination: { nextCursor: list.cursor, onLoadMore: list.loadMore, loading: list.loading && list.items.length > 0 } as PaginationProps,
    countText: n > 0 ? t("shell.list.shown", { n }) : undefined,
  };
}

/** Error of a "Load more" that failed while rows are already shown (the rows stay). */
export function MoreError<T>({ list }: { list: CursorList<T> }) {
  if (!list.error || list.items.length === 0) return null;
  return <OrgError error={list.error} onRetry={list.cursor ? list.loadMore : () => void list.reload()} className="mt-3" />;
}
