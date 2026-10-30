"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { fmtApiDate } from "@/lib/format";
import { pickLocalized } from "@/lib/lms/localized";
import type { SharedBankRowOut } from "@/lib/lms/types";
import { Badge, Button, LoadingState } from "@/components/ui";

/**
 * Phase 9 S2 (PHASE_9_DESIGN 4.2, 8.1): banks shared in a tree, as cards (full width at 375 px). `action` renders
 * the one action of a card (open the bank in the org area, "Copy into this course" in the course picker).
 */
export function SharedBankList({ items, loading, hasMore, onMore, action }: {
  items: SharedBankRowOut[];
  loading: boolean;
  hasMore: boolean;
  onMore: () => void;
  action: (b: SharedBankRowOut) => React.ReactNode;
}) {
  const { lang, t } = useTranslation();
  return (
    <div className="space-y-3">
      {items.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2">
          {items.map((b) => (
            <li key={b.id} className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="min-w-0 break-words font-semibold text-slate-900">{b.title}</span>
                  <Badge tone="info">{t("sharedBanks.badge")}</Badge>
                </p>
                <p className="mt-1 break-words text-sm text-slate-600">
                  {t("sharedBanks.from", { course: pickLocalized(b.course_title, lang) || "—", org: b.organization_name })}
                </p>
                {b.description && <p className="mt-1 line-clamp-2 break-words text-sm text-slate-600">{b.description}</p>}
                <p className="mt-2 text-xs text-slate-600">{t("bank.list.counts", { questions: b.question_count, passages: b.passage_count })}</p>
                {(b.shared_by || b.shared_at) && (
                  <p className="text-xs text-slate-600">
                    {b.shared_by ? t("sharedBanks.sharedBy", { name: b.shared_by.display_name || b.shared_by.email }) : ""}
                    {b.shared_by && b.shared_at ? " · " : ""}
                    {b.shared_at ? fmtApiDate(b.shared_at, lang) : ""}
                  </p>
                )}
              </div>
              <div>{action(b)}</div>
            </li>
          ))}
        </ul>
      )}
      {loading && <LoadingState label={t("lms.common.loading")} rows={items.length ? 1 : 2} />}
      {hasMore && !loading && (
        <Button variant="secondary" onClick={onMore} className="w-full sm:w-auto">{t("sharedBanks.more")}</Button>
      )}
    </div>
  );
}
