"use client";

// Step 3a S3 (STUDENT_IA_DESIGN §2.2, §2.3, §7.1-§7.3): the student's courses grouped ОРТ · НЦТ · Другие курсы on the
// hub (4 cards per group + «Все курсы … (N)» → `/courses#family`) and on «Мои курсы» (every card, anchors `#ort`,
// `#nct`, `#other`). Each card (`HubCourseCard`): cover, title, provider, progress, for exam courses a small countdown,
// the last result line and one next-step button from the server's `next_step` (no client-side visibility rule: the
// server sends only what the student may open).
import React from "react";
import Link from "next/link";
import { ArrowRight, CalendarClock, Trophy } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { examDayStart } from "@/components/ui/Countdown";
import { groupCourses } from "@/lib/lms/examFamilies";
import type { HomeCourseOut, HomeNextStepOut } from "@/lib/lms/homeTypes";
import { lessonStepHref } from "@/lib/lms/lastPlace";
import { pickLocalized } from "@/lib/lms/localized";
import { LinkButton, cn, focusRing } from "@/components/ui";
import { CourseCard } from "@/components/lms/course/CourseCard";
import { useGradeListText } from "@/components/lms/results/GradeBadge";

/** As many 256–360 px columns as fit the container (one at 375 px, two next to the hub's side column at 1440 px);
 * the same grid as the old home's (`ExamPrepHome`, deleted in S5). */
const HOME_CARD_GRID = "grid gap-4 grid-cols-[repeat(auto-fill,minmax(min(100%,256px),360px))]";

/** Where the card's one button goes, and its label key (`home.hub.step.*`). */
export function nextStepLink(lang: string, courseId: string, step: HomeNextStepOut | null | undefined): { href: string; label: string } {
  const base = `/${lang}/courses/${courseId}`;
  if (step?.kind === "resume_test" && step.attempt_id) return { href: `${base}/attempts/${step.attempt_id}`, label: "home.hub.step.resume_test" };
  if (step?.kind === "continue_lesson") {
    const href = lessonStepHref(lang, courseId, { module_id: step.module_id, item_id: step.item_id, kind: step.item_kind, link: step.link });
    if (href) return { href, label: "home.hub.step.continue_lesson" };
  }
  if (step?.kind === "start") {
    if (step.assessment_id) return { href: `${base}/assessments/${step.assessment_id}`, label: "home.hub.step.start" };
    if (step.assignment_id) return { href: `${base}/assignments/${step.assignment_id}`, label: "home.hub.step.startAssignment" };
  }
  return { href: base, label: "home.hub.step.open" };
}

/** «До экзамена 30 дн.» / «Экзамен сегодня»; nothing without a date or after the exam day. */
function ExamCountdown({ date }: { date: string }) {
  const { t } = useTranslation();
  // the same count as the course header's countdown tiles (whole days to the start of the exam day, Bishkek time);
  // under a day, and during the exam day itself: «Экзамен сегодня»; after it: nothing
  const ms = examDayStart(date).getTime() - Date.now();
  if (ms <= -86_400_000) return null;
  const days = Math.floor(ms / 86_400_000);
  return (
    <p className="flex items-center gap-1.5 text-sm font-medium leading-5 text-slate-700">
      <CalendarClock aria-hidden="true" className="h-4 w-4 shrink-0 text-brand-600" />
      <span className="min-w-0">{days < 1 ? t("home.hub.card.examToday") : t("home.hub.card.examIn", { count: days })}</span>
    </p>
  );
}

export function HubCourseCard({ course, examTitle, headingLevel }: { course: HomeCourseOut; examTitle?: string | null; headingLevel: 3 | 4 }) {
  const { lang, t } = useTranslation();
  const gradeText = useGradeListText();
  const step = nextStepLink(lang, course.id, course.next_step);
  const last = course.last_result
    ? gradeText({ display_value: course.last_result.value, max_value: course.last_result.max_value, label: course.last_result.label,
      labels: course.last_result.labels, scheme_type: course.last_result.scheme_type })
    : "";
  return (
    <CourseCard course={course} href={`/${lang}/courses/${course.id}`} headingLevel={headingLevel} progress={course.progress} nextDue={course.next_due_at}
      action={(
        <div className="space-y-2">
          {examTitle && <p className="break-words text-sm leading-5 text-slate-600">{t("home.hub.card.forExam", { exam: examTitle })}</p>}
          {course.exam_date && <ExamCountdown date={course.exam_date} />}
          {last && (
            <p className="flex items-center gap-1.5 text-sm leading-5 text-slate-700">
              <Trophy aria-hidden="true" className="h-4 w-4 shrink-0 text-gold-600" />
              <span className="min-w-0 break-words">{t("home.hub.card.lastResult", { value: last })}</span>
            </p>
          )}
          <LinkButton href={step.href} variant="secondary" size="sm" rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />}>
            {t(step.label)}
          </LinkButton>
        </div>
      )} />
  );
}

/**
 * The grouped cards. `cap`: cards per group (the hub; then «Все курсы … (N)» → `/courses#family`); none: every card
 * (`/courses`). `level`: the heading level of the group titles (cards one below).
 */
export function CourseGroups({ courses, cap, level }: { courses: HomeCourseOut[]; cap?: number; level: 2 | 3 }) {
  const { lang, t } = useTranslation();
  const groups = groupCourses(courses);
  const byId = new Map(courses.map((c) => [c.id, c]));
  const examTitle = (c: HomeCourseOut) => {
    const exam = c.exam_course_id ? byId.get(c.exam_course_id) : undefined;
    return exam ? pickLocalized(exam.title, lang, exam.default_language) || null : null;
  };
  const H = level === 2 ? "h2" : "h3";
  return (
    <div className="space-y-6">
      {groups.map((g) => {
        const shown = cap ? g.courses.slice(0, cap) : g.courses;
        const id = `group-${g.key}`;
        return (
          <section key={g.key} id={cap ? undefined : g.key} aria-labelledby={id} className="min-w-0 scroll-mt-24">
            <H id={id} className="mb-2 text-base font-semibold uppercase leading-6 tracking-wide text-slate-700">
              {t(`home.hub.groups.${g.key}`)}
              {cap && g.courses.length > 1 ? <>{" "}<span className="font-medium normal-case text-slate-500">({g.courses.length})</span></> : null}
            </H>
            <ul className={HOME_CARD_GRID}>
              {shown.map((c) => <HubCourseCard key={c.id} course={c} examTitle={examTitle(c)} headingLevel={level === 2 ? 3 : 4} />)}
            </ul>
            {cap && g.courses.length > shown.length && (
              <Link href={`/${lang}/courses#${g.key}`}
                className={cn("mt-2 inline-flex min-h-11 items-center gap-1 rounded text-sm font-medium text-brand-700 hover:underline", focusRing)}>
                {t(`home.hub.allInGroup.${g.key}`, { n: g.courses.length })}
                <ArrowRight aria-hidden="true" className="h-4 w-4" />
              </Link>
            )}
          </section>
        );
      })}
    </div>
  );
}
