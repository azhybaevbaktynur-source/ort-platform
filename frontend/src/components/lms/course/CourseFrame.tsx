"use client";

// Step 3a S2 (docs/phases/STUDENT_IA_DESIGN.md §3.1, §3.2, §3.5, §6.7): the frame of one course space for its students
// (Student view included), above every page of the course except the player (`PLAYER_FRAME`).
//
// - `full` (Обзор): cover strip, the course title as the page's h1, the meta line (provider, language, counts), «К
//   экзамену: …» for a lesson course attached to an exam, exam courses the countdown tiles and the goal line
//   (`ExamHeaderBlock`), the progress bar (`courseProgress`), then the tabs.
// - `compact` (other tabs, object pages): one title line linking to Обзор (not a heading: the page's own title is its
//   h1, one h1 per page), then the tabs with the parent tab current.
// - Tabs are links in `<nav aria-label="Разделы курса">` with `aria-current="page"`, 44 px targets, horizontal scroll on
//   phones (the current tab is scrolled into view, never clipped), and a prefetch of the tab's reads on hover, focus or
//   touch. Which tabs exist is the server's (`courseTabs`, `CourseOut.features`).
// - Pro bar: the tab that holds locked content draws `ProCallout variant="course"` first under the tabs (Уроки with a
//   locked module, Тесты with a paid test and no pass, the lobby of a paid test); Обзор has the unlock card instead.
import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { getCourseLanding, type CourseLandingOut } from "@/lib/lms/catalog";
import { courseProgress } from "@/lib/lms/courseProgress";
import type { CourseTab, CourseTabsResult } from "@/lib/lms/courseTabs";
import { pickLocalized } from "@/lib/lms/localized";
import { prefetchAnalytics, prefetchExamPrep, prefetchModules, useExamPrep, useStudentModules } from "@/lib/lms/pageData";
import { useCached, type SwrOptions } from "@/lib/lms/swr";
import { templateUi } from "@/lib/lms/templates";
import type { CourseOut } from "@/lib/lms/types";
import { cn, focusRing } from "@/components/ui";
import { STUDENT_TITLE } from "@/components/lms/student/StudentPageHeader";
import { useStudentShellDataContext } from "@/components/lms/student/StudentShellDataContext";
import { courseProgress as lessonProgress, lessonList } from "@/components/lms/modules/lessons";
import { CourseCardCover } from "./CourseCardCover";
import { ExamCountdown, ExamGoalLine } from "./ExamHeaderBlock";

const COURSE_CACHE: SwrOptions = { ttl: 60_000, storage: "session" };
const FADE = "linear-gradient(to right, #000 calc(100% - 32px), transparent)";
const LESSON_KINDS = new Set(["page", "file", "url"]);

export function isExamCourse(course: CourseOut): boolean {
  return templateUi(course).studentLayout === "exam_prep";
}

function CourseTabsNav({ course, tabs, className }: { course: CourseOut; tabs: CourseTab[]; className?: string }) {
  const { t } = useTranslation();
  const navRef = useRef<HTMLElement>(null);
  const exam = isExamCourse(course);
  const f = course.features;
  const activeKey = tabs.find((x) => x.active)?.key ?? null;
  // more tabs to the right of the visible strip: the right edge fades out as a hint (a mask, no extra element)
  const [more, setMore] = useState(false);
  const measure = () => {
    const nav = navRef.current;
    if (nav) setMore(nav.scrollLeft + nav.clientWidth < nav.scrollWidth - 4);
  };
  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [tabs.length]);
  // the current tab is in view on a phone (scroll the strip, never the page)
  useEffect(() => {
    const nav = navRef.current;
    const el = nav?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!nav || !el) return;
    const left = el.offsetLeft - 16;
    const right = el.offsetLeft + el.offsetWidth + 16;
    if (left < nav.scrollLeft) nav.scrollLeft = Math.max(0, left);
    else if (right > nav.scrollLeft + nav.clientWidth) nav.scrollLeft = right - nav.clientWidth;
    measure();
  }, [activeKey]);
  const prefetch = (tab: CourseTab) => () => {
    if (tab.key === "lessons" && f?.modules) prefetchModules(course.id);
    else if (tab.key === "overview") (exam ? prefetchExamPrep(course.id) : f?.modules ? prefetchModules(course.id) : undefined);
    else if (tab.key === "tests" && exam) prefetchExamPrep(course.id);
    else if (tab.key === "analytics" && f?.tests) prefetchAnalytics(course.id);
  };
  // a focused tab scrolled out of the strip comes back into view
  const reveal = (e: React.FocusEvent<HTMLAnchorElement>) => {
    const nav = navRef.current;
    const el = e.currentTarget;
    if (!nav) return;
    if (el.offsetLeft < nav.scrollLeft) nav.scrollLeft = el.offsetLeft - 16;
    else if (el.offsetLeft + el.offsetWidth > nav.scrollLeft + nav.clientWidth) nav.scrollLeft = el.offsetLeft + el.offsetWidth - nav.clientWidth + 16;
    measure();
  };
  return (
    <nav ref={navRef} aria-label={t("course.tabs.label")} onScroll={measure}
      style={more ? { WebkitMaskImage: FADE, maskImage: FADE } : undefined} className={cn("relative -mx-1 overflow-x-auto overscroll-x-contain [scrollbar-width:none]", className)}>
      <ul className="flex min-w-max gap-1 px-1">
        {tabs.map((tab) => (
          <li key={tab.key}>
            <Link href={tab.href} aria-current={tab.active ? "page" : undefined}
              onMouseEnter={prefetch(tab)} onTouchStart={prefetch(tab)}
              onFocus={(e) => { prefetch(tab)(); reveal(e); }}
              className={cn("relative inline-flex min-h-11 items-center whitespace-nowrap rounded-t-lg px-3 text-sm font-semibold leading-5 transition-colors",
                focusRing, "focus-visible:ring-offset-0",
                tab.active
                  ? "text-brand-800 after:absolute after:inset-x-2 after:bottom-0 after:h-[3px] after:rounded-full after:bg-brand-600"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900")}>
              {tab.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** «К экзамену: ОРТ (на русском)» of a lesson course attached to an exam: the title from the student's own course list
 * (the shell already has it), else from the exam's catalog landing (platform exams are listed); nothing when neither
 * answers. */
function ForExamLine({ examId }: { examId: string }) {
  const { lang, t } = useTranslation();
  const shell = useStudentShellDataContext();
  const mine = shell?.courses.find((c) => c.id === examId) ?? null;
  const waitShell = !!shell && !shell.loaded;
  const { data } = useCached<CourseLandingOut>(mine || waitShell ? null : `catalog-landing:${examId}`, () => getCourseLanding(examId), COURSE_CACHE);
  const title = mine ? pickLocalized(mine.title, lang, mine.default_language) : data ? pickLocalized(data.title, lang) : "";
  if (!title) return null;
  return (
    <p className="mt-1 text-sm leading-5 text-slate-700">
      {t("course.header.forExam")}{" "}
      <Link href={mine ? `/${lang}/courses/${examId}` : `/${lang}/courses/catalog/${examId}`}
        className={cn("rounded font-medium text-brand-700 underline-offset-2 hover:underline", focusRing)}>{title}</Link>
    </p>
  );
}

function FullHeader({ course, tabs }: { course: CourseOut; tabs: CourseTab[] }) {
  const { lang, t } = useTranslation();
  const exam = isExamCourse(course);
  const { data: prep } = useExamPrep(exam ? course.id : null);
  const { data: modules } = useStudentModules(course.id, !!course.features?.modules);
  const title = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");
  const provider = course.is_platform_course ? t("courses.home.providerPlatform") : course.owner_display_name;
  const lessons = modules ? lessonList(modules.modules) : [];
  const lessonCount = lessons.filter((l) => LESSON_KINDS.has(l.item.kind)).length;
  const meta = [
    provider,
    t(`courses.languages.${course.default_language}`),
    exam && prep ? t("courses.card.tests", { count: prep.library_total }) : null,
    lessonCount > 0 ? t("courses.card.lessons", { count: lessonCount }) : null,
  ].filter(Boolean).join(" · ");
  const progress = courseProgress({ modules: modules && lessons.length > 0 ? lessonProgress(modules, lessons) : null });
  const progressText = progress ? t("course.header.progress", { done: progress.done, total: progress.total }) : "";
  return (
    <header className="mb-5 overflow-hidden rounded-card border border-slate-200 bg-white sm:mb-6">
      <CourseCardCover courseId={course.id} platform={course.is_platform_course} coverUrl={course.cover_url}
        className="aspect-auto h-[120px] lg:h-[160px]" />
      <div className="flex flex-col gap-4 px-4 pb-2 pt-4 sm:px-5 sm:pt-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-2">
          <div>
            <h1 className={STUDENT_TITLE}>{title}</h1>
            {meta && <p className="mt-1 break-words text-sm leading-5 text-slate-600">{meta}</p>}
            {course.exam_course_id && <ForExamLine examId={course.exam_course_id} />}
          </div>
          {exam && <ExamGoalLine prep={prep} courseId={course.id} />}
          {progress && (
            <div className="max-w-md">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm leading-5">
                <span className="font-medium tabular-nums text-slate-800">{progressText}</span>
                <span className="tabular-nums text-slate-600">{t("course.header.percent", { percent: progress.percent })}</span>
              </div>
              <div role="progressbar" aria-label={t("course.header.progressLabel")} aria-valuemin={0} aria-valuemax={progress.total}
                aria-valuenow={progress.done} aria-valuetext={progressText} className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-brand-600" style={{ width: `${progress.percent}%` }} />
              </div>
            </div>
          )}
        </div>
        {exam && <ExamCountdown prep={prep} />}
      </div>
      <CourseTabsNav course={course} tabs={tabs} className="border-t border-slate-100 px-3 sm:px-4" />
    </header>
  );
}

function CompactHeader({ course, tabs }: { course: CourseOut; tabs: CourseTab[] }) {
  const { lang, t } = useTranslation();
  const title = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");
  return (
    <header className="mb-5 border-b border-slate-200 sm:mb-6">
      <p className="min-w-0">
        <Link href={`/${lang}/courses/${course.id}`}
          className={cn("inline-block max-w-full truncate rounded text-base font-semibold leading-6 text-slate-900 hover:text-brand-700 sm:text-lg sm:leading-7", focusRing)}>
          {title}
        </Link>
      </p>
      <CourseTabsNav course={course} tabs={tabs} className="mt-1" />
    </header>
  );
}

export function CourseFrame({ course, tabs }: { course: CourseOut; tabs: CourseTabsResult }) {
  return tabs.variant === "full" ? <FullHeader course={course} tabs={tabs.tabs} /> : <CompactHeader course={course} tabs={tabs.tabs} />;
}
