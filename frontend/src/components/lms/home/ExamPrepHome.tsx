"use client";

// Student UI U3 (STUDENT_UI_DESIGN §3.1): the home of a student with an exam-prep course (the student shell's current
// course). Greeting with the mascot and the exam countdown, the one "Next" card (the page's only primary button), the
// streak strip and the current / target scores, the gold unlock card while some tests need a pass, the sections of the
// latest result, then the student's courses and the platform courses to join. Three reads in parallel (`/me/home` by
// the caller, the exam-prep page and the last 7 days of activity); a skeleton first; the page works without activity.
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Check, KeyRound, Plus, Target, TrendingUp, Trophy } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { getExamPrep, wholeNumber, type ExamGoalOut, type ExamPrepOut } from "@/lib/lms/examPrep";
import { getActivity, type ActivityOut } from "@/lib/lms/progress";
import type { HomeOut } from "@/lib/lms/homeTypes";
import type { LocalizedText } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import {
  Badge, Button, Countdown, ErrorState, GoldPill, Mascot, Meter, STAT_ICON_TONE, SectionTag, Skeleton, cn, examDayStart, focusRing,
  type StatIconTone,
} from "@/components/ui";
import { STUDENT_TITLE } from "@/components/lms/student/StudentPageHeader";
import { NextCard } from "@/components/lms/examPrep/NextCard";
import { GoalEditor, fmtExamDate } from "@/components/lms/examPrep/GoalStrip";
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
  // pattern as the other student pages (§5.1 d): title, small subtitle, one thing on the right (the countdown)
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
      ) : !date ? (
        <p className="text-sm leading-5 text-slate-600 lg:max-w-xs lg:text-right">{t("home.prep.noDate")}</p>
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
    <section aria-labelledby="home-score" className={cn("grid grid-cols-2 gap-3 sm:gap-4", className)}>
      <h2 id="home-score" className="sr-only">{t("home.prep.score.title")}</h2>
      <div className={tile}>
        <TileLabel icon={<TrendingUp />} tone="blue">{t("home.prep.score.current")}</TileLabel>
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
        <TileLabel icon={<Target />} tone="orange">{t("examPrep.goal.targetLabel")}</TileLabel>
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

function UnlockCard() {
  const { lang, t } = useTranslation();
  const items = ["includedExams", "includedPractice", "includedResults"];
  return (
    <section aria-labelledby="home-unlock"
      className="flex flex-col gap-4 rounded-card border border-gold-300 bg-gradient-to-br from-gold-50 to-gold-100 p-4 sm:flex-row sm:items-center sm:p-5">
      <Mascot pose="encouraging" size={88} className="hidden sm:block" />
      <div className="min-w-0 flex-1">
        <h2 id="home-unlock" className="text-lg font-semibold leading-7 text-gold-900">{t("home.prep.unlock.title")}</h2>
        <p className="mt-0.5 text-base leading-6 text-slate-800 sm:text-sm sm:leading-5">{t("home.prep.unlock.body")}</p>
        <ul className="mt-2 space-y-1">
          {items.map((k) => (
            <li key={k} className="flex items-start gap-2 text-sm leading-5 text-slate-800">
              <Check aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-gold-700" strokeWidth={3} />
              <span className="min-w-0 break-words">{t(`access.unlock.${k}`)}</span>
            </li>
          ))}
        </ul>
      </div>
      <GoldPill href={`/${lang}/unlock`} className="justify-center sm:shrink-0">{t("access.needsPassLink")}</GoldPill>
    </section>
  );
}

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
              return (
                <li key={s.key} className="grid grid-cols-1 gap-1.5 sm:grid-cols-[12.5rem_minmax(0,1fr)_5rem] sm:items-center sm:gap-3">
                  <span className="min-w-0"><SectionTag section={s.key} /></span>
                  <Meter value={pct} label={`${name}: ${score}`} />
                  <span className="hidden text-right text-sm tabular-nums text-slate-600 sm:block">{score}</span>
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
      <div className="grid gap-4 lg:grid-cols-2">
        <StreakCardSkeleton />
        <div className="grid grid-cols-2 gap-3 sm:gap-4">
          <Skeleton className="h-36 w-full rounded-card" />
          <Skeleton className="h-36 w-full rounded-card" />
        </div>
      </div>
      <Skeleton className="h-52 w-full rounded-card" />
    </div>
  );
}

/** The courses row: the student's courses, a card to the catalog, then the platform courses to join. */
export function CoursesRow({ courses, platform }: { courses: React.ReactNode; platform: HomeOut["platform_courses"] }) {
  const { lang, t } = useTranslation();
  return (
    <div className="space-y-6">
      <section aria-labelledby="home-courses" className="min-w-0">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="home-courses" className="text-lg font-semibold leading-7 text-slate-900">{t("home.courses.title")}</h2>
          <Link href={`/${lang}/courses/join`}
            className={cn("inline-flex min-h-11 items-center gap-1.5 rounded text-sm font-medium text-brand-700 hover:underline sm:min-h-0", focusRing)}>
            <KeyRound aria-hidden="true" className="h-4 w-4" />{t("home.primary.join")}
          </Link>
        </div>
        {courses}
      </section>
      <PlatformCourses courses={platform ?? []} grid={HOME_CARD_GRID} joinVariant="secondary" />
    </div>
  );
}

/** The "+" card at the end of the course grid. */
export function CatalogCard() {
  const { lang, t } = useTranslation();
  return (
    <li className="min-w-0">
      <Link href={`/${lang}/courses/catalog`}
        className={cn("flex h-full min-h-[8rem] flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed border-slate-300 p-4 text-center text-sm font-medium text-slate-700 hover:border-brand-300 hover:bg-brand-50/50 hover:text-brand-800", focusRing)}>
        <span aria-hidden="true" className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100"><Plus className="h-5 w-5" /></span>
        {t("home.prep.addCourse")}
      </Link>
    </li>
  );
}

export function ExamPrepHome({ courseId, courseTitle, home, side, courses, embedded = false }: {
  courseId: string;
  courseTitle: LocalizedText | null;
  /** `/me/home`, null while it loads (the courses row shows its own skeleton or error) */
  home: HomeOut | null;
  /** to-do, grades and announcements of other courses (rendered by the caller) */
  side: React.ReactNode;
  courses: React.ReactNode;
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

  // personal best: the newest released result of this course beats the student's other attempts
  const best = !!home?.latest_results.find((r) => r.course_id === courseId)?.is_personal_best;
  const hasResult = (prep?.history.length ?? 0) > 0 || (home?.latest_results.length ?? 0) > 0;

  return (
    <div className="w-full space-y-6">
      <Hero title={courseTitle} prep={prep} best={best} embedded={embedded} />
      {prepError && !prep ? (
        <ErrorState message={errorText(prepError)} onRetry={() => void loadPrep()} retrying={prepLoading} />
      ) : !prep ? (
        <PrepSkeleton />
      ) : (
        <>
          <NextCard next={prep.next} courseId={courseId} accent className="rounded-card shadow-none" />
          <div className={cn("grid gap-4", activityState !== "failed" && "lg:grid-cols-2")}>
            {activityState === "loading" && <StreakCardSkeleton />}
            {activity && <StreakCard activity={activity} />}
            <ScoreTiles prep={prep} courseId={courseId} best={best} onGoal={(goal) => setPrep({ ...prep, goal })} />
          </div>
          {/* §5.1 b: the gold card only for a student without any released result; the sidebar pill is always there */}
          {prep.needs_pass && !hasResult && <UnlockCard />}
          <div className={cn("flex flex-col gap-6", side && "lg:grid lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start")}>
            <SectionRows prep={prep} />
            {side && <div className="min-w-0 space-y-6">{side}</div>}
          </div>
        </>
      )}
      <CoursesRow courses={courses} platform={home?.platform_courses} />
    </div>
  );
}
