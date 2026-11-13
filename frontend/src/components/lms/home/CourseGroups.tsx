"use client";

// Step 3a S3 (STUDENT_IA_DESIGN §2.2, §7.1-§7.3): the student's courses grouped ОРТ · НЦТ · Другие курсы on the hub
// (4 cards per group; S7 v3 V7: «Все курсы … (N)» expands the group in place, «Свернуть» collapses it; the «Мои курсы»
// page and its `/courses#family` anchors are gone). Each card (`HubCourseCard`): cover, title, provider, progress, for
// exam courses a small countdown, the last result line and one next-step button from the server's `next_step` (no
// client-side visibility rule: the server sends only what the student may open).
import React, { useState } from "react";
import { ArrowRight, CalendarClock, ChevronDown, ChevronUp, Trophy } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { examDayStart } from "@/components/ui/Countdown";
import { groupCourses } from "@/lib/lms/examFamilies";
import type { HomeCourseOut } from "@/lib/lms/homeTypes";
import { nextStepLink } from "@/lib/lms/lastPlace";
import { pickLocalized } from "@/lib/lms/localized";
import { LinkButton, Spinner, cn, focusRing } from "@/components/ui";
import { CourseCard } from "@/components/lms/course/CourseCard";
import { useGradeListText } from "@/components/lms/results/GradeBadge";

/** As many 256–360 px columns as fit the container (one at 375 px, two next to the hub's side column at 1440 px);
 * the same grid as the old home's (`ExamPrepHome`, deleted in S5). */
const HOME_CARD_GRID = "grid gap-4 grid-cols-[repeat(auto-fill,minmax(min(100%,256px),360px))]";


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

/** `compact`: the hub's lower cover on phones (96 px instead of 150; the catalog keeps its own). */
export function HubCourseCard({ course, examTitle, headingLevel, compact = false }: {
  course: HomeCourseOut; examTitle?: string | null; headingLevel: 3 | 4; compact?: boolean;
}) {
  const { lang, t } = useTranslation();
  const gradeText = useGradeListText();
  const step = nextStepLink(lang, course.id, course.next_step);
  const last = course.last_result
    ? gradeText({ display_value: course.last_result.value, max_value: course.last_result.max_value, label: course.last_result.label,
      labels: course.last_result.labels, scheme_type: course.last_result.scheme_type })
    : "";
  return (
    <CourseCard course={course} href={`/${lang}/courses/${course.id}`} headingLevel={headingLevel} progress={course.progress} nextDue={course.next_due_at} coverClassName={compact ? "max-sm:h-24" : undefined}
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
 * The grouped cards. `cap`: cards per group, then «Все курсы … (N)», a button that shows the rest in place (client
 * state only); none: every card. `level`: the heading level of the group titles (cards one below). `complete` false:
 * the list holds fewer courses than the student has (the bootstrap holds up to 50), so the first expand asks
 * `onNeedAll` once (`loadingAll` while it runs).
 */
export function CourseGroups({ courses, cap, level, complete = true, onNeedAll, loadingAll = false }: {
  courses: HomeCourseOut[]; cap?: number; level: 2 | 3; complete?: boolean; onNeedAll?: () => void; loadingAll?: boolean;
}) {
  const { lang, t } = useTranslation();
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const toggle = (key: string) => {
    const next = new Set(open);
    if (next.has(key)) next.delete(key);
    else {
      next.add(key);
      if (!complete) onNeedAll?.();
    }
    setOpen(next);
  };
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
        const expanded = open.has(g.key);
        const capped = !!cap && g.courses.length > cap;
        const shown = cap && !expanded ? g.courses.slice(0, cap) : g.courses;
        const id = `group-${g.key}`;
        const listId = `group-${g.key}-list`;
        return (
          <section key={g.key} aria-labelledby={id} className="min-w-0">
            <H id={id} className="mb-2 text-base font-semibold leading-6 text-slate-800">
              {t(`home.hub.groups.${g.key}`)}
              {" "}<span className="font-medium text-slate-500">({g.courses.length})</span>
            </H>
            <ul id={listId} className={HOME_CARD_GRID} aria-busy={(expanded && loadingAll) || undefined}>
              {shown.map((c) => <HubCourseCard key={c.id} course={c} examTitle={examTitle(c)} headingLevel={level === 2 ? 3 : 4} compact={!!cap} />)}
            </ul>
            {(capped || (expanded && !!cap)) && (
              <button type="button" aria-expanded={expanded} aria-controls={listId} onClick={() => toggle(g.key)}
                className={cn("mt-2 inline-flex min-h-11 items-center gap-1 rounded text-sm font-medium text-brand-700 hover:underline", focusRing)}>
                {expanded ? t("home.hub.collapseGroup") : t(`home.hub.allInGroup.${g.key}`, { n: g.courses.length })}
                {expanded && loadingAll ? <Spinner className="h-4 w-4" />
                  : expanded ? <ChevronUp aria-hidden="true" className="h-4 w-4" /> : <ChevronDown aria-hidden="true" className="h-4 w-4" />}
              </button>
            )}
          </section>
        );
      })}
    </div>
  );
}
