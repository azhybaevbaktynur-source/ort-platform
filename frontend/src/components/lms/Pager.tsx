"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";

/** Cursor pager: shows a "load more" button while the server has another page. */
export function Pager({ nextCursor, loading, onMore }: { nextCursor: string | null; loading?: boolean; onMore: () => void }) {
  const { t } = useTranslation();
  if (!nextCursor) return null;
  return (
    <div className="mt-4 flex justify-center">
      <button type="button" disabled={loading} onClick={onMore}
        className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">
        {loading ? t("lms.common.loading") : t("lms.common.loadMore")}
      </button>
    </div>
  );
}
