"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { EmptyState, ErrorState, SectionTag, Skeleton, Tabs } from "@/components/ui";
import { Pager } from "@/components/lms/Pager";
import { ReviewItemCard } from "@/components/lms/results/ReviewItemCard";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { listMistakes, type MistakeOut, type MistakeStatus } from "@/lib/lms/progress";

/** Mistakes notebook: open (latest answer wrong) or fixed (answered right since), a card per question. */
export function MistakesList({ courseId }: { courseId: string }) {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const [status, setStatus] = useState<MistakeStatus>("open");
  const [items, setItems] = useState<MistakeOut[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listMistakes(courseId, status, next);
      setItems((prev) => (next && prev ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [courseId, status]);
  useEffect(() => { setItems(null); void load(); }, [load]);

  const tabsId = "mistakes-filter";
  return (
    <div className="space-y-4">
      <Tabs id={tabsId} label={t("progress.mistakes.filter")} value={status} onChange={(v) => setStatus(v as MistakeStatus)}
        items={[{ id: "open", label: t("progress.mistakes.open") }, { id: "fixed", label: t("progress.mistakes.fixed") }]} />
      {error ? <ErrorState message={errorText(error)} onRetry={() => void load(items ? cursor : undefined)} retrying={loading} /> : null}
      {!error && items === null && <div className="space-y-3"><Skeleton className="h-40 w-full" /><Skeleton className="h-40 w-full" /></div>}
      {!error && items !== null && items.length === 0 && (
        <EmptyState mascot={status === "open" ? "celebrating" : "reading"} title={t(status === "open" ? "progress.mistakes.emptyOpen" : "progress.mistakes.emptyFixed")}
          description={status === "open" ? undefined : t("progress.analytics.mistakes.emptyFixedHint")} />
      )}
      {items !== null && items.length > 0 && (
        <ul className="space-y-6">
          {items.map((m, i) => (
            <li key={`${m.attempt_id}:${m.item.position}`} className="space-y-2">
              {/* Student UI U6: the notebook in the analytics style (section tag, test, topic, date) */}
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm leading-5 text-slate-600">
                  {m.section && <SectionTag section={m.section} />}
                  <span className="min-w-0 break-words font-medium text-slate-800">{pickLocalized(m.assessment_title, lang) || t("assessments.untitled")}</span>
                  {m.topic && <span className="min-w-0 break-words">· {m.topic}</span>}
                  {m.submitted_at && <span>· {fmtShortDateTime(m.submitted_at, lang)}</span>}
                </p>
                <Link href={`/${lang}/courses/${courseId}/attempts/${m.attempt_id}/result#item-${m.item.position}`} className="inline-flex min-h-11 items-center text-sm font-semibold text-brand-700 hover:underline sm:min-h-0">
                  {t("progress.mistakes.viewAttempt")}
                </Link>
              </div>
              <ReviewItemCard item={m.item} number={i + 1} maxPoints={m.item.points} />
            </li>
          ))}
        </ul>
      )}
      <Pager nextCursor={cursor} loading={loading} onMore={() => void load(cursor)} />
    </div>
  );
}
