"use client";

// Student UI U3 (STUDENT_UI_DESIGN §3.1): the streak strip of the home. The current streak in words with a flame, the
// longest one, and the last seven days as dots (a check on a day with answers; the day's name says it for screen
// readers, so colour is never the only signal). Data: `GET /courses/{c}/my/activity?days=7`; the home hides the card
// when that read fails.
import React from "react";
import { Check, Flame } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { ActivityOut } from "@/lib/lms/progress";
import { Skeleton, cn } from "@/components/ui";

export const HOME_CARD = "min-w-0 rounded-card border border-slate-200 bg-white p-4 sm:p-5";

function dayNames(iso: string, lang: string): { short: string; long: string } {
  const date = new Date(`${iso}T00:00:00Z`);
  const locale = lang === "en" ? "en-GB" : lang;
  try {
    return {
      short: date.toLocaleDateString(locale, { weekday: "short", timeZone: "UTC" }),
      long: date.toLocaleDateString(locale, { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }),
    };
  } catch {
    return { short: iso.slice(8), long: iso };
  }
}

export function StreakCardSkeleton({ className }: { className?: string }) {
  return (
    <div aria-hidden="true" className={cn(HOME_CARD, className)}>
      <Skeleton className="h-5 w-32" />
      <Skeleton className="mt-3 h-8 w-40" />
      <div className="mt-4 grid grid-cols-7 gap-1">
        {Array.from({ length: 7 }, (_, i) => <Skeleton key={i} className="mx-auto h-9 w-9 rounded-full" />)}
      </div>
    </div>
  );
}

export function StreakCard({ activity, className }: { activity: ActivityOut; className?: string }) {
  const { lang, t } = useTranslation();
  const days = activity.days.slice(-7);
  const streak = activity.streak_current;
  return (
    <section aria-labelledby="home-streak" className={cn(HOME_CARD, className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id="home-streak" className="text-base font-semibold leading-6 text-slate-900">{t("progress.analytics.tiles.streak")}</h2>
        {activity.streak_longest > 0 && (
          <p className="text-sm leading-5 text-slate-600">{t("progress.analytics.tiles.streakBest", { count: activity.streak_longest })}</p>
        )}
      </div>
      {streak > 0 ? (
        <p className="mt-2 flex items-center gap-2">
          <Flame aria-hidden="true" className="h-7 w-7 shrink-0 fill-chart-3/20 text-chart-3" />
          <span className="text-2xl font-bold leading-8 tabular-nums text-slate-900">{t("home.prep.streak.days", { count: streak })}</span>
        </p>
      ) : (
        <p className="mt-2 text-base leading-6 text-slate-700 sm:text-sm sm:leading-5">{t("home.prep.streak.none")}</p>
      )}
      <ol aria-label={t("home.prep.streak.week")} className="mt-4 grid grid-cols-7 gap-1">
        {days.map((d, i) => {
          const names = dayNames(d.date, lang);
          const active = d.answered > 0;
          const today = i === days.length - 1;
          return (
            <li key={d.date} className="flex min-w-0 flex-col items-center gap-1.5">
              <span className="sr-only">{t(active ? "home.prep.streak.dayActive" : "home.prep.streak.dayIdle", { day: names.long })}</span>
              <span aria-hidden="true"
                className={cn("flex h-9 w-9 items-center justify-center rounded-full border-2",
                  active ? "border-brand-600 bg-brand-600 text-white" : "border-slate-200 bg-white",
                  today && "ring-2 ring-brand-200 ring-offset-1")}>
                {active && <Check className="h-4 w-4" strokeWidth={3} />}
              </span>
              <span aria-hidden="true" className={cn("max-w-full truncate text-xs leading-4", today ? "font-semibold text-slate-900" : "text-slate-600")}>
                {names.short}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
