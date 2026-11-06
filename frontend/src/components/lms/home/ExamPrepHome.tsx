"use client";

// Student UI U3 (STUDENT_UI_DESIGN §3.1): the home of a student with an exam-prep course (the student shell's current
// course). Greeting with the mascot and the exam countdown (only with a date), the one "Next" card (the page's only
// primary button), the last / target scores, the streak strip, the short gold unlock card while some tests need a pass
// and no result exists, the sections of the latest result, then the platform courses to join and the student's other
// courses. U9 (STUDENT_UI_REVIEW): no course grids; switching, the catalog, the code and leaving live in the shell's
// exam sheet. Three reads in parallel (`/me/home` by the caller, the exam-prep page and the last 7 days of activity).
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight, Pencil, Target, TrendingUp, Trophy } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { getExamPrep, wholeNumber, type ExamGoalOut, type ExamPrepOut } from "@/lib/lms/examPrep";
import { getActivity, type ActivityOut } from "@/lib/lms/progress";
import type { HomeOut } from "@/lib/lms/homeTypes";
import type { LocalizedText } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import {
  Badge, Button, Countdown, ErrorState, GoldPill, IconButton, Mascot, Meter, STAT_ICON_TONE, SectionTag, Skeleton, cn, examDayStart,
  focusRing, type StatIconTone,
} from "@/components/ui";
import { STUDENT_TITLE } from "@/components/lms/student/StudentPageHeader";
import { NextCard } from "@/components/lms/examPrep/NextCard";
import { GoalEditor, fmtExamDate } from "@/components/lms/examPrep/GoalStrip";
import { noteExamPrep } from "@/components/lms/student/gettingStarted"; // Student UI U8
import { PlatformCourses } from "./PlatformCourses";
import { HOME_CARD, StreakCard, StreakCardSkeleton } from "./StreakCard";
import { useErrorText } from "./useErrorText";

/** Course cards: as many 16rem columns as fit (one at 375 px, never thin at 1920 px). */
export const HOME_CARD_GRID = "grid grid-cols-[repeat(auto-fill,minmax(16rem,1fr))] gap-4";

type GreetingPart = "morning" | "afternoon" | "evening";
function partOfDay(hour: number): GreetingPart {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 18) return "afternoon";
  return "evening";
}

/** "Добрый день, Айбек" by the device's hour; the first word of the display name. */
export function useGreeting(): string {
  const { t } = useTranslation();
  const { me } = useLmsMe();
  const part = partOfDay(new Date().getHours());
  const first = (me?.display_name ?? "").trim().split(/\s+/)[0] ?? "";
  return first ? t(`home.greeting.${part}`, { name: first }) : t(`home.greeting.${part}Plain`);
}

const num = (v: string | number) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};
const plain = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));
const label = "text-sm font-medium leading-5 text-slate-600";
const big = "text-[2rem] font-bold leading-9 tabular-nums text-slate-900";

function Hero({ title, prep, best, embedded }: {
  title: LocalizedText | null; prep: ExamPrepOut | null; best: boolean; embedded: boolean;
}) {
  const { lang, t } = useTranslation();
  const greeting = useGreeting();
  const Title = embedded ? "h2" : "h1";
  const date = prep?.exam_date ?? null;
  const target = date ? examDayStart(date) : null;
  const over = !!target && Date.now() - target.getTime() >= 86_400_000; // the exam day has passed
  const course = pickLocalized(title, lang);
  // Student UI colour (§1.1): the greeting sits in the sky band (#dff1ff → #f5fbff) with the mascot; the same header
  // pattern as the other student pages (§5.1 d): title, small subtitle, one thing on the right (the countdown).
  // U9 (review 12): without a date there is no countdown and no system message.
  return (
    <header className="flex flex-col gap-4 rounded-card border border-[#cde5fa] bg-gradient-to-br from-[#dff1ff] to-[#f5fbff] p-4 sm:p-6 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 items-center gap-3 sm:gap-4">
        <Mascot pose={best ? "celebrating" : "hello"} size={88} eager className="h-16 w-auto sm:h-[88px]" />
        <div className="min-w-0">
          <Title className={STUDENT_TITLE}>{greeting}</Title>
          <p className="mt-1 break-words text-sm leading-5 text-slate-700">
            {course}
            {course && date && !over ? " · " : ""}
            {date && !over ? t("examPrep.goal.examOn", { date: fmtExamDate(date, lang) }) : ""}
          </p>
        </div>
      </div>
      {!prep ? (
        <Skeleton aria-hidden="true" className="h-[4.25rem] w-full rounded-control lg:w-[19rem]" />
      ) : target && !over ? (
        <div className="w-full lg:w-[19rem] lg:shrink-0">
          <p aria-hidden="true" className="mb-1.5 text-xs font-semibold uppercase leading-4 tracking-wide text-slate-600">{t("examPrep.goal.daysLabel")}</p>
          <Countdown target={target} label={t("examPrep.goal.daysLabel")} />
        </div>
      ) : null}
    </header>
  );
}

/** A tile's label with its coloured icon chip (§1.1 stat tiles). */
function TileLabel({ icon, tone, children }: { icon: React.ReactNode; tone: StatIconTone; children: React.ReactNode }) {
  return (
    <p className={cn(label, "flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:gap-2.5")}>
      <span aria-hidden="true" className={cn("inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl [&>svg]:h-5 [&>svg]:w-5", STAT_ICON_TONE[tone])}>
        {icon}
      </span>
      <span className="min-w-0 break-words">{children}</span>
    </p>
  );
}

/** With a result: the last score and the goal as two tiles. */
function ScoreTiles({ prep, courseId, best, onGoal, className }: {
  prep: ExamPrepOut; courseId: string; best: boolean; onGoal: (g: ExamGoalOut) => void; className?: string;
}) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const target = prep.goal.target_score;
  const latest = wholeNumber(prep.latest?.value);
  const max = wholeNumber(prep.goal.scale_max);
  const gap = target !== null && latest !== null ? target - latest : null;
  const tile = cn(HOME_CARD, "flex flex-col");
  return (
    <section id="home-score" aria-labelledby="home-score-title" className={cn("grid grid-cols-2 gap-3 sm:gap-4", className)}>
      <h2 id="home-score-title" className="sr-only">{t("home.prep.score.title")}</h2>
      <div className={tile}>
        <TileLabel icon={<TrendingUp />} tone="brand">{t("examPrep.goal.latestLabel")}</TileLabel>
        {latest !== null ? (
          <>
            <p className="mt-1 flex flex-wrap items-baseline gap-x-2">
              <span className={big}>{latest}</span>
              {max !== null && <span className="text-sm font-medium text-slate-700">{t("examPrep.goal.outOf", { max })}</span>}
            </p>
            <div className="mt-auto flex flex-wrap gap-2 pt-2">
              {best && <Badge icon={<Trophy aria-hidden="true" />} className="border-gold-300 bg-gold-100 text-gold-900">{t("home.personalBest")}</Badge>}
              {gap !== null && (gap <= 0
                ? <Badge icon={<Trophy aria-hidden="true" />} className="border-gold-300 bg-gold-100 text-gold-900">{t("examPrep.goal.reached")}</Badge>
                : <p className="text-sm leading-5 text-slate-600">{t("examPrep.goal.toTarget", { count: gap })}</p>)}
            </div>
          </>
        ) : (
          <p className="mt-1 text-sm leading-5 text-slate-600">{t("examPrep.goal.noScore")}</p>
        )}
      </div>
      <div className={tile}>
        <TileLabel icon={<Target />} tone="brand">{t("examPrep.goal.targetLabel")}</TileLabel>
        {target !== null ? (
          <>
            <p className={cn(big, "mt-1")}>{target}</p>
            <div className="mt-auto pt-1">
              <Button variant="link" onClick={() => setEditing(true)} aria-expanded={editing}>{t("examPrep.goal.edit")}</Button>
            </div>
          </>
        ) : (
          <>
            <p className="mt-1 text-sm leading-5 text-slate-600">{t("examPrep.goal.noTarget")}</p>
            <div className="mt-auto pt-2">
              <Button variant="secondary" size="sm" onClick={() => setEditing(true)} aria-expanded={editing}>{t("examPrep.goal.setTarget")}</Button>
            </div>
          </>
        )}
      </div>
      {editing && (
        <GoalEditor courseId={courseId} goal={prep.goal} className="col-span-2 rounded-card shadow-none sm:col-span-2"
          onDone={(g) => { onGoal(g); setEditing(false); }} onCancel={() => setEditing(false)} />
      )}
    </section>
  );
}

/** U9 (review 4): before the first result, score and goal as one slim row; the goal is edited in place. */
function ScoreLine({ prep, courseId, onGoal }: { prep: ExamPrepOut; courseId: string; onGoal: (g: ExamGoalOut) => void }) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const target = prep.goal.target_score;
  const part = "inline-flex items-baseline gap-1.5 whitespace-nowrap";
  const value = "font-semibold tabular-nums text-slate-900";
  return (
    <section id="home-score" aria-labelledby="home-score-title" className={cn(HOME_CARD, "py-2 sm:py-2")}>
      <h2 id="home-score-title" className="sr-only">{t("home.prep.score.title")}</h2>
      <div className="flex flex-wrap items-center gap-x-2 text-sm leading-5 text-slate-700 sm:gap-x-3">
        <span className={part}>{t("examPrep.goal.latestLabel")}: <span className={value}>—</span></span>
        <span aria-hidden="true" className="text-slate-400">·</span>
        <span className="inline-flex items-center gap-1">
          <span className={part}>{t("examPrep.goal.targetLabel")}: <span className={value}>{target ?? "—"}</span></span>
          <IconButton icon={<Pencil />} aria-label={target === null ? t("examPrep.goal.setTarget") : t("examPrep.goal.edit")}
            onClick={() => setEditing(true)} aria-expanded={editing} className="text-brand-700" />
        </span>
      </div>
      {editing && (
        <GoalEditor courseId={courseId} goal={prep.goal} className="mb-2 mt-1 rounded-card shadow-none"
          onDone={(g) => { onGoal(g); setEditing(false); }} onCancel={() => setEditing(false)} />
      )}
    </section>
  );
}

/** §5.1 b, U9 (review 9): one short gold card for a student without results; the details stay on /unlock. */
function UnlockCard() {
  const { lang, t } = useTranslation();
  return (
    <section aria-labelledby="home-unlock"
      className="flex flex-col gap-3 rounded-card border border-gold-300 bg-gradient-to-br from-gold-50 to-gold-100 p-4 sm:flex-row sm:items-center sm:gap-4 sm:px-5">
      <div className="min-w-0 flex-1">
        <h2 id="home-unlock" className="text-base font-semibold leading-6 text-gold-900">{t("home.prep.unlock.title")}</h2>
        <p className="text-base leading-6 text-slate-800 sm:text-sm sm:leading-5">{t("home.prep.unlock.body")}</p>
      </div>
      <GoldPill href={`/${lang}/unlock`} className="justify-center sm:shrink-0">{t("access.needsPassLink")}</GoldPill>
    </section>
  );
}

/** Same rule as the server's `SectionStat.rated` (10 graded answers); the stored result keeps points, one per item. */
const SECTION_MIN_RATED = 10;

function SectionRows({ prep, className }: { prep: ExamPrepOut; className?: string }) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="home-sections" className={cn(HOME_CARD, className)}>
      <h2 id="home-sections" className="text-base font-semibold leading-6 text-slate-900">{t("examPrep.sections.title")}</h2>
      {prep.sections.length === 0 ? (
        <p className="mt-2 text-base leading-6 text-slate-600 sm:text-sm sm:leading-5">{t("examPrep.sections.empty")}</p>
      ) : (
        <>
          <p className="text-sm leading-5 text-slate-600">{t("examPrep.sections.subtitle")}</p>
          <ul className="mt-4 space-y-3">
            {prep.sections.map((s) => {
              const raw = num(s.raw);
              const possible = num(s.possible);
              const pct = possible > 0 ? (raw / possible) * 100 : 0;
              const name = t(`sections.${s.key}`);
              const score = t("examPrep.sections.score", { raw: plain(raw), possible: plain(possible) });
              // STUDENT_UI_FIX_PLAN 4.3: too few questions in the section: the raw "n из m", no band colour, no percent
              const rated = possible >= SECTION_MIN_RATED;
              return (
                <li key={s.key} className="grid grid-cols-1 gap-1.5 sm:grid-cols-[12.5rem_minmax(0,1fr)_5rem] sm:items-center sm:gap-3">
                  <span className="min-w-0"><SectionTag section={s.key} /></span>
                  {rated ? <Meter value={pct} label={`${name}: ${score}`} /> : (
                    <div role="img" aria-label={`${name}: ${score}. ${t("examPrep.sections.fewAnswers")}`} title={t("examPrep.sections.fewAnswers")}
                      className="h-2 min-w-0 overflow-hidden rounded-full bg-slate-100">
                      <div className="h-full rounded-full bg-slate-300" style={{ width: `${pct}%` }} />
                    </div>
                  )}
                  <span className={cn("text-right text-sm tabular-nums text-slate-600", rated ? "hidden sm:block" : "sm:block")}>{score}</span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

function PrepSkeleton() {
  return (
    <div aria-hidden="true" className="space-y-4 sm:space-y-6">
      <Skeleton className="h-32 w-full rounded-card sm:h-24" />
      <Skeleton className="h-14 w-full rounded-card" />
      <StreakCardSkeleton />
    </div>
  );
}

/** U9 (review 1): the student's courses outside the exam switcher (teacher-made courses) as one compact list. */
function OtherCourses({ home }: { home: HomeOut }) {
  const { lang, t } = useTranslation();
  const other = home.courses.filter((c) => c.student_layout !== "exam_prep");
  if (other.length === 0) return null;
  return (
    <section aria-labelledby="home-other-courses" className="min-w-0">
      <h2 id="home-other-courses" className="mb-2 text-lg font-semibold leading-7 text-slate-900">{t("home.prep.otherCourses")}</h2>
      <ul className="divide-y divide-slate-100 rounded-card border border-slate-200 bg-white">
        {other.map((c) => (
          <li key={c.id}>
            <Link href={`/${lang}/courses/${c.id}`}
              className={cn("flex min-h-12 items-center gap-3 rounded-card px-4 py-2 text-base font-medium leading-6 text-slate-900 hover:bg-slate-50 sm:text-sm sm:leading-5", focusRing, "focus-visible:ring-offset-0")}>
              <span className="min-w-0 flex-1 break-words">{pickLocalized(c.title, lang, c.default_language) || t("courses.list.untitled")}</span>
              <ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-400" />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ExamPrepHome({ courseId, courseTitle, home, homeError, side, embedded = false }: {
  courseId: string;
  courseTitle: LocalizedText | null;
  /** `/me/home`, null while it loads */
  home: HomeOut | null;
  /** the `/me/home` error with its retry (shown where the course lists go) */
  homeError?: React.ReactNode;
  /** to-do, grades and announcements of other courses (rendered by the caller) */
  side: React.ReactNode;
  embedded?: boolean;
}) {
  const errorText = useErrorText();
  const [prep, setPrep] = useState<ExamPrepOut | null>(null);
  const [prepError, setPrepError] = useState<unknown>(null);
  const [prepLoading, setPrepLoading] = useState(true);
  const [activity, setActivity] = useState<ActivityOut | null>(null);
  const [activityState, setActivityState] = useState<"loading" | "ok" | "failed">("loading");

  const loadPrep = useCallback(async (signal?: AbortSignal) => {
    setPrepLoading(true);
    setPrepError(null);
    try {
      const out = await getExamPrep(courseId, signal);
      if (!signal?.aborted) setPrep(out);
    } catch (e) {
      if (!signal?.aborted) setPrepError(e);
    } finally {
      if (!signal?.aborted) setPrepLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    const ctl = new AbortController();
    setPrep(null);
    setActivity(null);
    setActivityState("loading");
    void loadPrep(ctl.signal);
    getActivity(courseId, 7, ctl.signal).then(
      (a) => { if (!ctl.signal.aborted) { setActivity(a); setActivityState("ok"); } },
      () => { if (!ctl.signal.aborted) setActivityState("failed"); },
    );
    return () => ctl.abort();
  }, [courseId, loadPrep]);

  // U8: the "Начало работы" checklist (sidebar pill and sheet) reads the goal and results from this page's answer
  useEffect(() => { if (prep) noteExamPrep(courseId, prep); }, [courseId, prep]);

  // personal best: the newest released result of this course beats the student's other attempts
  const best = !!home?.latest_results.find((r) => r.course_id === courseId)?.is_personal_best;
  const hasResult = (prep?.history.length ?? 0) > 0 || (home?.latest_results.length ?? 0) > 0;
  const scored = (prep?.history.length ?? 0) > 0 || !!prep?.latest; // this course has a result
  const setGoal = (goal: ExamGoalOut) => { if (prep) setPrep({ ...prep, goal }); };
  const sections = !!prep && prep.history.length > 0; // U9 (review 4): the sections card only after a result

  return (
    <div className="w-full space-y-6">
      <Hero title={courseTitle} prep={prep} best={best} embedded={embedded} />
      {prepError && !prep ? (
        <ErrorState message={errorText(prepError)} onRetry={() => void loadPrep()} retrying={prepLoading} />
      ) : !prep ? (
        <PrepSkeleton />
      ) : (
        <>
          <NextCard next={prep.next} courseId={courseId} className="rounded-card shadow-none" />
          {scored ? (
            <div className={cn("grid gap-4", activityState !== "failed" && "lg:grid-cols-2")}>
              {activityState === "loading" && <StreakCardSkeleton />}
              {activity && <StreakCard activity={activity} />}
              <ScoreTiles prep={prep} courseId={courseId} best={best} onGoal={setGoal} />
            </div>
          ) : (
            <>
              <ScoreLine prep={prep} courseId={courseId} onGoal={setGoal} />
              {activityState === "loading" && <StreakCardSkeleton />}
              {activity && <StreakCard activity={activity} />}
            </>
          )}
          {/* §5.1 b: the gold card only for a student without any released result; the sidebar pill is always there */}
          {prep.needs_pass && !hasResult && <UnlockCard />}
          {(sections || side) && (
            <div className={cn("flex flex-col gap-6", sections && side && "lg:grid lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start")}>
              {sections && <SectionRows prep={prep} />}
              {side && <div className={cn("min-w-0 space-y-6", !sections && "lg:grid lg:grid-cols-2 lg:gap-6 lg:space-y-0")}>{side}</div>}
            </div>
          )}
        </>
      )}
      {home ? (
        <>
          <PlatformCourses courses={home.platform_courses ?? []} compact />
          <OtherCourses home={home} />
        </>
      ) : homeError}
    </div>
  );
}
