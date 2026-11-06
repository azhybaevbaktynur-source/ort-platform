"use client";

// Exam prep S2: every published test as a card (status, best released score), filtered by source. The sources are
// the course's published modules (teachers already group tests by source in modules); tests in no module are "Other".
// Paginated ("Show more"). Each card keeps an empty slot beside its status for the lock of paid tests (S3).
import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Clock, ListChecks } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { SOURCE_OTHER, listExamLibrary, wholeNumber, type ExamSourceOut, type LibraryCardOut, type LibraryStatus } from "@/lib/lms/examPrep";
import { Badge, ErrorState, Pagination, Skeleton, cn, type BadgeTone } from "@/components/ui";
import { fmtDuration } from "@/components/lms/home/format";
import { useErrorText } from "@/components/lms/home/useErrorText";

const STATUS_TONE: Record<LibraryStatus, BadgeTone> = { not_started: "neutral", in_progress: "info", done: "success" };
const GRID = "grid gap-4 sm:grid-cols-2 xl:grid-cols-3";

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={active} onClick={onClick}
      className={cn("inline-flex min-h-11 max-w-full items-center rounded-full border px-4 text-sm font-medium leading-5 transition-colors sm:min-h-9",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2",
        active ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50")}>
      <span className="truncate">{children}</span>
    </button>
  );
}

function TestCard({ card, href }: { card: LibraryCardOut; href: string }) {
  const { lang, t } = useTranslation();
  const title = pickLocalized(card.title, lang) || t("assessments.untitled");
  const best = wholeNumber(card.best_value);
  const max = wholeNumber(card.scale_max);
  const duration = fmtDuration(card.time_limit_s, t);
  return (
    <li className="group relative flex min-w-0 flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-2">
        <Badge tone={STATUS_TONE[card.status]}>{t(`examPrep.library.status.${card.status}`)}</Badge>
        {/* S3: the lock of a paid test goes here; empty now */}
        <span aria-hidden="true" data-slot="lock" className="h-6 w-6 shrink-0" />
      </div>
      <h3 className="break-words text-base font-semibold leading-6 text-slate-900">
        <Link href={href}
          className="rounded after:absolute after:inset-0 after:rounded-2xl group-hover:underline focus:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-brand-500">
          {title}
        </Link>
      </h3>
      <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm leading-5 text-slate-600">
        <span className="inline-flex items-center gap-1.5"><ListChecks aria-hidden="true" className="h-4 w-4" />{t("home.questions", { n: card.item_count, count: card.item_count })}</span>
        {duration && <span className="inline-flex items-center gap-1.5"><Clock aria-hidden="true" className="h-4 w-4" />{duration}</span>}
      </p>
      {(best !== null || card.best_percent !== null || card.status === "done") && (
        <div className="mt-auto border-t border-slate-100 pt-3">
          {best !== null ? (
            <p className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-sm text-slate-600">{t("examPrep.library.best")}</span>
              <span className="text-2xl font-bold leading-8 tabular-nums text-slate-900">{best}</span>
              {max !== null && <span className="text-sm text-slate-600">{t("examPrep.goal.outOf", { max })}</span>}
            </p>
          ) : card.best_percent !== null ? (
            <p className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-sm text-slate-600">{t("examPrep.library.bestPercent")}</span>
              <span className="text-2xl font-bold leading-8 tabular-nums text-slate-900">{Math.round(card.best_percent)}%</span>
            </p>
          ) : (
            <p className="text-sm leading-5 text-slate-600">{t("examPrep.library.pending")}</p>
          )}
        </div>
      )}
    </li>
  );
}

export function TestLibrary({ courseId, sources, total, className }: {
  courseId: string; sources: ExamSourceOut[]; total: number; className?: string;
}) {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const [source, setSource] = useState<string | null>(null);
  const [items, setItems] = useState<LibraryCardOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const seq = useRef(0);
  const base = `/${lang}/courses/${courseId}`;

  const load = useCallback(async (next?: string | null) => {
    const mine = ++seq.current; // a newer filter wins over a slower older page
    setLoading(true);
    setError(null);
    try {
      const page = await listExamLibrary(courseId, { source, cursor: next });
      if (mine !== seq.current) return;
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      if (mine === seq.current) setError(e);
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [courseId, source]);
  useEffect(() => { void load(); }, [load]);

  const href = (c: LibraryCardOut) => `${base}/assessments/${c.id}`; // the lobby: start, continue or see the results

  return (
    <section aria-labelledby="exam-library" className={cn("min-w-0", className)}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id="exam-library" className="text-lg font-semibold leading-7 text-slate-900">{t("examPrep.library.title")}</h2>
        {total > 0 && <p className="text-sm text-slate-600">{t("examPrep.library.count", { count: total })}</p>}
      </div>
      {sources.length > 0 && (
        <div role="group" aria-label={t("examPrep.library.filter")} className="mb-4 flex flex-wrap gap-2">
          <Chip active={source === null} onClick={() => setSource(null)}>{t("examPrep.library.all")}</Chip>
          {sources.map((s) => {
            const key = s.module_id ?? SOURCE_OTHER;
            return (
              <Chip key={key} active={source === key} onClick={() => setSource(key)}>
                {s.module_id ? pickLocalized(s.title, lang) || t("examPrep.library.other") : t("examPrep.library.other")}
              </Chip>
            );
          })}
        </div>
      )}
      {error && items.length === 0 ? <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} /> : null}
      {loading && items.length === 0 && !error && (
        <div role="status" aria-live="polite">
          <span className="sr-only">{t("ui.loading")}</span>
          <div aria-hidden="true" className={GRID}>{[0, 1, 2].map((i) => <Skeleton key={i} className="h-44 w-full rounded-2xl" />)}</div>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <p className="rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-6 text-center text-base leading-6 text-slate-600">
          {source ? t("examPrep.library.emptyFilter") : t("examPrep.library.empty")}
        </p>
      )}
      {items.length > 0 && (
        <ul className={GRID} aria-busy={loading || undefined}>
          {items.map((c) => <TestCard key={c.id} card={c} href={href(c)} />)}
        </ul>
      )}
      {error && items.length > 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} className="mt-3" /> : null}
      <Pagination nextCursor={cursor} loading={loading} onLoadMore={() => void load(cursor)} />
    </section>
  );
}
