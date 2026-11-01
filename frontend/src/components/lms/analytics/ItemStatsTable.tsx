"use client";

// Phase 10 S5: per-question statistics of one quiz version. Table on wide screens, cards at phone width (the same
// markup, a grid that stacks). Hidden for readers without item access (org admins get 403).
import React, { useCallback, useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { isLmsApiError } from "@/lib/lms/client";
import { listQuizItemStats, type ItemSort, type OptionStat, type QuizItemStat } from "@/lib/lms/statistics";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Badge, Button, EmptyState, LoadingState, Select } from "@/components/ui";

const LOW_DISCRIMINATION = 0.2;
const GRID = "sm:grid sm:grid-cols-[3rem_minmax(0,1fr)_5rem_6rem_5rem_2rem] sm:items-center sm:gap-3";

export function ItemStatsTable({ courseId, assessmentId, versionId, reloadKey }: {
  courseId: string; assessmentId: string; versionId: string | null; reloadKey: string;
}) {
  const { t } = useTranslation();
  const [sort, setSort] = useState<ItemSort>("hardest");
  const [items, setItems] = useState<QuizItemStat[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [hidden, setHidden] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async (next?: string | null) => {
    if (next) setMore(true); else setLoading(true);
    setError(null);
    try {
      const page = await listQuizItemStats(courseId, assessmentId, { versionId, sort, cursor: next, limit: 25 });
      setItems((p) => (next ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      if (isLmsApiError(e) && e.status === 403) setHidden(true); else setError(e);
    } finally { setLoading(false); setMore(false); }
  }, [courseId, assessmentId, versionId, sort]);
  useEffect(() => { void load(); }, [load, reloadKey]);

  if (hidden) return null;

  const optionLabel = (o: OptionStat) =>
    o.label === "true" ? t("quizStats.optTrue") : o.label === "false" ? t("quizStats.optFalse") : o.label;

  return (
    <section aria-labelledby="qs-items" className="mt-8">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <h2 id="qs-items" className="text-lg font-semibold text-slate-900">{t("quizStats.itemsTitle")}</h2>
        <Select
          label={t("quizStats.sortLabel")}
          value={sort}
          onChange={(ev) => { setSort(ev.target.value as ItemSort); setOpen(null); }}
          options={[{ value: "hardest", label: t("quizStats.sortHardest") }, { value: "slot", label: t("quizStats.sortSlot") }]}
          containerClassName="w-full sm:w-56"
        />
      </div>
      <ErrorMessage error={error} onRetry={() => void load()} />
      {loading ? <LoadingState rows={4} /> : items.length === 0 && !error ? (
        <EmptyState title={t("quizStats.itemsEmpty")} />
      ) : (
        <div className="rounded-xl border border-slate-200 bg-white">
          <div className={`hidden border-b border-slate-200 px-4 py-2 text-xs font-medium text-slate-600 ${GRID}`} aria-hidden="true">
            <span>#</span><span>{t("quizStats.colQuestion")}</span>
            <span>{t("quizStats.colAccuracy")}</span><span>{t("quizStats.colDiscrimination")}</span><span>{t("quizStats.colTime")}</span><span />
          </div>
          <ul className="divide-y divide-slate-200">
            {items.map((it) => {
              const isOpen = open === it.id;
              const low = it.point_biserial !== null && it.point_biserial < LOW_DISCRIMINATION;
              return (
                <li key={it.id}>
                  <button
                    type="button"
                    aria-expanded={isOpen}
                    onClick={() => setOpen(isOpen ? null : it.id)}
                    className={`w-full px-4 py-3 text-left hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 ${GRID}`}
                  >
                    <span className="text-sm font-medium text-slate-700">{it.slot}</span>
                    <span className="mt-1 block min-w-0 break-words text-sm text-slate-900 sm:mt-0">{it.stem_excerpt || t("quizStats.noText")}</span>
                    <span className="mt-2 flex items-center gap-2 text-sm sm:mt-0 sm:block">
                      <span className="text-xs text-slate-600 sm:hidden">{t("quizStats.colAccuracy")}</span>
                      <span className="font-semibold tabular-nums text-slate-900">{Math.round(it.accuracy)}%</span>
                    </span>
                    <span className="mt-1 flex items-center gap-2 text-sm sm:mt-0 sm:block">
                      <span className="text-xs text-slate-600 sm:hidden">{t("quizStats.colDiscrimination")}</span>
                      {it.point_biserial === null ? <span className="text-slate-600">-</span> : (
                        <span className="tabular-nums" title={low ? t("quizStats.lowDiscrimination") : undefined}>
                          {it.point_biserial.toFixed(2)}
                          {low && <Badge tone="warning" className="ml-1">{t("quizStats.low")}</Badge>}
                        </span>
                      )}
                    </span>
                    <span className="mt-1 flex items-center gap-2 text-sm tabular-nums sm:mt-0 sm:block">
                      <span className="text-xs text-slate-600 sm:hidden">{t("quizStats.colTime")}</span>
                      {it.avg_seconds === null ? "-" : t("quizStats.approxSeconds", { n: it.avg_seconds })}
                    </span>
                    <ChevronDown aria-hidden="true" className={`hidden h-4 w-4 text-slate-600 transition-transform sm:block ${isOpen ? "rotate-180" : ""}`} />
                  </button>
                  {isOpen && (
                    <div className="border-t border-slate-100 bg-slate-50 px-4 py-3">
                      <p className="text-xs text-slate-600">
                        {t("quizStats.answerSummary", { n: it.n, correct: it.correct, partial: it.partial, incorrect: it.incorrect, unanswered: it.unanswered })}
                      </p>
                      {it.options && it.options.length > 0 && (
                        <ul className="mt-2 space-y-1">
                          {it.options.map((o) => (
                            <li key={o.key} className="flex items-center justify-between gap-3 text-sm">
                              <span className="min-w-0 break-words text-slate-900">
                                {optionLabel(o)}
                                {o.is_correct && <Badge tone="success" className="ml-2">{t("quizStats.correctOption")}</Badge>}
                              </span>
                              <span className="shrink-0 tabular-nums text-slate-700">{o.count}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {cursor && !loading && (
        <div className="mt-3 flex justify-center">
          <Button variant="secondary" loading={more} onClick={() => void load(cursor)}>{t("quizStats.showMore")}</Button>
        </div>
      )}
    </section>
  );
}
