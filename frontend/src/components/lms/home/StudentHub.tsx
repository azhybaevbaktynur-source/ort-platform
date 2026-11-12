"use client";

// Step 3a S3 (STUDENT_IA_DESIGN §2.2, §7.1-§7.3): Главная `/home`, a hub only. The greeting; one «Продолжить» card (the
// remembered last place, else the server fallback: the in-progress attempt, the first next lesson, the newest exam
// course's Обзор; a quiet «Серия N дней» line from the bootstrap's cross-course activity when N >= 2); «Мои курсы»
// grouped ОРТ · НЦТ · Другие курсы (4 cards per group); «К выполнению» across courses with the announcement rows (OPEN
// Q1); the notices that live on the home. No test list, results list or statistics. One API round on a fresh load: the
// shell's `GET /me/bootstrap?include=home` carries `/me/home` and the activity (`pageData.ts`, P2). A student sees only
// what the server sends.
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Flame, KeyRound, Megaphone, Plus, Sparkles } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { loadHome, peekHomeActivity } from "@/lib/lms/pageData";
import type { HomeCourseOut, HomeOut } from "@/lib/lms/homeTypes";
import { continueTarget, type ContinueTarget } from "@/lib/lms/lastPlace";
import { useLastPlaceRead } from "@/lib/lms/useLastPlace";
import { HUB_GROUP_MAX } from "@/lib/lms/examFamilies";
import { chooseCoursesHref } from "@/lib/lms/chooseCourses";
import { pickLocalized } from "@/lib/lms/localized";
import { LMS_ME_STALE_EVENT } from "@/lib/lms/meStale";
import type { ActivityOut } from "@/lib/lms/progress";
import { EmptyState, ErrorState, LinkButton, Mascot, Skeleton, cn, focusRing } from "@/components/ui";
import { STUDENT_TITLE } from "@/components/lms/student/StudentPageHeader";
import { useStudentShellDataContext } from "@/components/lms/student/StudentShellDataContext";
import { PendingApplicationsLine } from "@/components/lms/catalog/ApplicationStatus";
import { CourseGroups } from "./CourseGroups";
import { TeacherApplicationNotice } from "./TeacherApplicationNotice";
import { SideRow, SideSection, TodoRows } from "./TodoList";
import { fmtDayMonthTime } from "./format";
import { useGreeting } from "./greeting";
import { useErrorText } from "./useErrorText";

const CARD = "min-w-0 rounded-card border border-slate-200 bg-white p-4 sm:p-5";

/** The greeting; without the mascot above the empty state (which has its own). */
function Greeting({ mascot = true }: { mascot?: boolean }) {
  const greeting = useGreeting();
  return (
    <header className="flex min-w-0 items-center gap-3">
      {mascot && <Mascot pose="hello" size={64} eager className="h-12 w-auto sm:h-16" />}
      <h1 className={STUDENT_TITLE}>{greeting}</h1>
    </header>
  );
}

/** What the continue card says about its target: the course, the place, the button label and where it goes. */
function useContinueText(target: ContinueTarget, courses: HomeCourseOut[], home: HomeOut | null) {
  const { lang, t } = useTranslation();
  const course = courses.find((c) => c.id === target.courseId);
  const courseTitle = course ? pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled") : "";
  const href = target.href;
  // a course's Обзор stood for the course's own next step (`continueTarget`): its title and its label
  if (target.kind === "step" && target.stepLabel) {
    const title = course?.next_step?.title ? pickLocalized(course.next_step.title, lang) : "";
    return { courseTitle, place: title || t(target.stepLabel), action: t(target.stepLabel), href };
  }
  const attempt = home?.in_progress.find((r) => r.attempt_id === target.attemptId)
    ?? (target.kind === "place" && target.placeKind === "lobby" ? home?.in_progress.find((r) => r.course_id === target.courseId) : undefined);
  if (target.kind === "resume") {
    const title = attempt ? pickLocalized(attempt.assessment_title, lang) : "";
    return { courseTitle, place: [title, t("home.hub.inProgress")].filter(Boolean).join(" · "), action: t("home.hub.continueTest"), href };
  }
  if (target.kind === "lesson") {
    const row = home?.modules_next?.find((r) => r.course_id === target.courseId)
      ?? (course?.next_step?.kind === "continue_lesson" ? { title: course.next_step.title, module_title: undefined } : undefined);
    const place = [row?.module_title ? pickLocalized(row.module_title, lang) : "", row?.title ? pickLocalized(row.title, lang) : ""].filter(Boolean).join(" · ");
    return { courseTitle, place: place || t("home.hub.place.lesson"), action: t("home.hub.continueLesson"), href };
  }
  if (target.kind === "place" && target.placeKind) {
    const action = target.placeKind === "lesson" ? t("home.hub.continueLesson")
      : target.placeKind === "lobby" && attempt ? t("home.hub.continueTest") : t("home.hub.open");
    return { courseTitle, place: t(`home.hub.place.${target.placeKind}`), action, href };
  }
  return { courseTitle, place: t("home.hub.overview"), action: t("home.hub.open"), href };
}

/** The one «Продолжить» card: the page's only primary button; the quiet streak line below it. */
function ContinueCard({ target, courses, home, streak }: { target: ContinueTarget; courses: HomeCourseOut[]; home: HomeOut | null; streak: number }) {
  const { t } = useTranslation();
  const text = useContinueText(target, courses, home);
  return (
    <section aria-labelledby="hub-continue" className={cn(CARD, "border-[#cde5fa] bg-gradient-to-br from-[#dff1ff] to-[#f5fbff]")}>
      <h2 id="hub-continue" className="text-xs font-semibold uppercase leading-4 tracking-wide text-slate-600">{t("home.hub.continue")}</h2>
      <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <p className="break-words text-lg font-semibold leading-7 text-slate-900">{text.courseTitle}</p>
          <p className="mt-0.5 break-words text-sm leading-5 text-slate-700">{text.place}</p>
        </div>
        <LinkButton href={text.href} size="lg" className="w-full shrink-0 sm:w-auto" rightIcon={<ArrowRight aria-hidden="true" className="h-5 w-5" />}>
          {text.action}
        </LinkButton>
      </div>
      {streak >= 2 && (
        <p className="mt-3 flex items-center gap-1.5 text-sm font-medium leading-5 text-slate-700">
          <Flame aria-hidden="true" className="h-4 w-4 shrink-0 text-brand-600" />
          {t("home.hub.streak", { count: streak })}
        </p>
      )}
    </section>
  );
}

/** «К выполнению» across courses: the server's to-do rows (in-progress first, due dates, overdue flagged), each named
 * with its course, then the announcement rows (OPEN Q1: the newest three). */
function HubTodo({ home }: { home: HomeOut }) {
  const { lang, t } = useTranslation();
  const todo = home.todo ?? [];
  const news = (home.announcements ?? []).slice(0, 3);
  return (
    <SideSection id="home-todo" title={t("home.todo.title")}>
      {todo.length === 0 && news.length === 0 ? (
        <p className="px-3 py-3 text-base leading-6 text-slate-600 sm:text-sm">{t("home.hub.todoEmpty")}</p>
      ) : (
        <>
          {todo.length > 0 && <TodoRows rows={todo} />}
          {news.length > 0 && (
            <ul className={cn("divide-y divide-slate-100", todo.length > 0 && "border-t border-slate-100")}>
              {news.map((r) => (
                <SideRow key={r.id} href={`/${lang}/courses/${r.course_id}/announcements`}
                  icon={<Megaphone aria-hidden="true" className="mt-1 h-4 w-4 shrink-0 text-slate-500 sm:mt-0.5" />}
                  title={r.title}
                  lines={(
                    <>
                      <span className="block break-words">{pickLocalized(r.course_title, lang) || t("courses.list.untitled")}</span>
                      <span className="block">{t("home.hub.announcement")} · {fmtDayMonthTime(r.published_at, lang)}</span>
                    </>
                  )} />
              ))}
            </ul>
          )}
        </>
      )}
    </SideSection>
  );
}

function HubSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-live="polite" className="space-y-6">
      <span className="sr-only">{t("ui.loading")}</span>
      <div aria-hidden="true" className="space-y-6">
        <Skeleton className="h-28 w-full rounded-card" />
        <div className="grid gap-4 grid-cols-[repeat(auto-fill,minmax(min(100%,256px),360px))]">
          {[0, 1].map((i) => <Skeleton key={i} className="h-64 w-full rounded-2xl" />)}
        </div>
      </div>
    </div>
  );
}

function EmptyHub() {
  const { lang, t } = useTranslation();
  return (
    <EmptyState mascot="hello" title={t("home.hub.emptyTitle")} description={t("home.hub.emptyBody")}
      action={(
        <>
          <LinkButton size="lg" href={chooseCoursesHref(lang)} leftIcon={<Sparkles aria-hidden="true" className="h-5 w-5" />}>{t("home.hub.choose")}</LinkButton>
          <LinkButton size="lg" variant="secondary" href={`/${lang}/courses/join`} leftIcon={<KeyRound aria-hidden="true" className="h-5 w-5" />}>{t("home.hub.join")}</LinkButton>
        </>
      )} />
  );
}

export function StudentHub() {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const shell = useStudentShellDataContext();
  const testStudent = !!useAuth().userProfile?.is_test_student; // Student view: no choose step
  const { place } = useLastPlaceRead();
  const [home, setHome] = useState<HomeOut | null>(null);
  const [activity, setActivity] = useState<ActivityOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setHome(await loadHome()); // P2: from the shell's bootstrap on a fresh load (one request)
      setActivity(peekHomeActivity());
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);
  // PERFORMANCE_AUDIT S2: joining or leaving a course reads the hub again (no page reload)
  useEffect(() => {
    const stale = () => { void load(); };
    window.addEventListener(LMS_ME_STALE_EVENT, stale);
    return () => window.removeEventListener(LMS_ME_STALE_EVENT, stale);
  }, [load]);

  // the cards: the home's list when it holds every course (fresh), else the bootstrap's (up to 50, known at once from
  // its cache, so the groups draw before `/me/home` answers on a repeat visit)
  const homeComplete = !!home && home.courses.length >= home.courses_total;
  const courses: HomeCourseOut[] | null = homeComplete ? home!.courses : shell?.loaded ? shell.courses : home?.courses ?? null;
  const known = courses !== null;
  const empty = known && courses!.length === 0 && (!home || home.courses_total === 0);

  const notices = home ? (
    <>
      {home.teacher_application && <TeacherApplicationNotice application={home.teacher_application} />}
      <PendingApplicationsLine items={home.pending_applications ?? []} />
    </>
  ) : null;

  let body: React.ReactNode;
  if (!known && error) body = <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />;
  else if (!known) body = <HubSkeleton />;
  else if (empty) body = <EmptyHub />;
  else {
    const target = continueTarget(lang, place, courses!, home ? { in_progress: home.in_progress, modules_next: home.modules_next } : null);
    body = (
      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
        <div className="min-w-0 space-y-6">
          <ContinueCard target={target} courses={courses!} home={home} streak={activity?.streak_current ?? 0} />
          <section aria-labelledby="hub-courses" className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
              <h2 id="hub-courses" className="text-lg font-semibold leading-7 text-slate-900">{t("home.hub.coursesTitle")}</h2>
              {!testStudent && (
                <Link href={chooseCoursesHref(lang)}
                  className={cn("inline-flex min-h-11 items-center gap-1 rounded text-sm font-medium text-brand-700 hover:underline", focusRing)}>
                  <Plus aria-hidden="true" className="h-4 w-4" />{t("home.hub.addCourse")}
                </Link>
              )}
            </div>
            <CourseGroups courses={courses!} cap={HUB_GROUP_MAX} level={3} />
          </section>
        </div>
        <div className="min-w-0 space-y-6">
          {home ? <HubTodo home={home} /> : error ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load()} /> : (
            <Skeleton aria-hidden="true" className="h-40 w-full rounded-card" />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="w-full space-y-6">
      <Greeting mascot={!empty} />
      {notices}
      {body}
    </div>
  );
}
