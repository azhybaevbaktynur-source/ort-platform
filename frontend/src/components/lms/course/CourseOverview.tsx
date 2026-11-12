"use client";

// Step 3a S2 (docs/phases/STUDENT_IA_DESIGN.md §3.3, §7.4, §7.5): Обзор `/courses/{c}`, the one student course page of
// every course (ORT included, Student view too). Main column: Следующий шаг (exam courses: the exam-prep `NextCard`;
// other courses: the running or next assignment, else the next lesson), Последний результат (exam: scaled score +
// section bars; other: the latest released grade with its feedback), the latest announcement, the lessons teaser; side
// column «О курсе» (description, provider / teachers, language, counts, Материалы, lesson courses of an exam, mascot);
// then the gold unlock card and «Покинуть курс». A course whose home is a page shows that page first. Every block
// reads what the server publishes for this student (no client-side visibility decision); a block without content is
// not drawn, a failed read says so in its place.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronRight, FolderOpen, Megaphone, PlayCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listAnnouncements } from "@/lib/lms/announcements";
import { listAssignments } from "@/lib/lms/assignments";
import type { AssignmentStudentOut } from "@/lib/lms/assignmentTypes";
import { listPeople } from "@/lib/lms/courses";
import { wholeNumber } from "@/lib/lms/examPrep";
import { getMyGrades } from "@/lib/lms/grading";
import type { MyGradeOut } from "@/lib/lms/gradingTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { useExamPrep, useStudentModules } from "@/lib/lms/pageData";
import type { AnnouncementStudentOut } from "@/lib/lms/pagesTypes";
import type { StaffPublicOut } from "@/lib/lms/types";
import { parseApiDate } from "@/lib/format";
import { useCourse } from "@/components/lms/CourseContext";
import { ErrorState, LinkButton, Mascot, Skeleton, cn, focusRing } from "@/components/ui";
import { NextCard } from "@/components/lms/examPrep/NextCard";
import { SectionBars } from "@/components/lms/examPrep/SectionBars";
import { StudentAssignmentCard } from "@/components/lms/assignments/StudentAssignmentCard";
import { primaryAssignmentId, sortForStudent, studentAssignmentView } from "@/components/lms/assignments/studentAssignment";
import { useGradeListText } from "@/components/lms/results/GradeBadge";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { LeaveCourseLink } from "@/components/lms/home/LeaveCourseLink";
import { useLessonCourseRows } from "@/components/lms/home/LessonCourses";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { ItemKindIcon } from "@/components/lms/modules/moduleUi";
import { isDone, isLocked, lessonHref, lessonList, nextOpen, type LessonRef } from "@/components/lms/modules/lessons";
import { PageView } from "@/components/lms/pages/PageView";
import { noteExamPrep } from "@/components/lms/student/gettingStarted";
import { excerptText } from "./excerpt";
import { isExamCourse } from "./CourseFrame";
import { UnlockCard } from "./UnlockCard";

const CARD = "rounded-card border border-slate-200 bg-white p-4 sm:p-5";
const BLOCK_TITLE = "text-sm font-semibold uppercase leading-5 tracking-wide text-slate-600";
const LESSON_KINDS = new Set(["page", "file", "url"]);

function BlockLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className={cn("inline-flex min-h-11 items-center gap-1 rounded text-sm font-semibold text-brand-700 hover:underline sm:min-h-0", focusRing)}>
      {children}<ChevronRight aria-hidden="true" className="h-4 w-4" />
    </Link>
  );
}

function BlockSkeleton({ title }: { title: string }) {
  return (
    <section aria-busy="true" className={CARD}>
      <h2 className={BLOCK_TITLE}>{title}</h2>
      <Skeleton className="mt-2 h-7 w-2/3 max-w-sm" />
      <Skeleton className="mt-2 h-5 w-1/2 max-w-xs" />
    </section>
  );
}

/** The latest released result of an exam course: the scaled score and the section bars. */
function ExamResult({ prepLatest, max, sections, base }: {
  prepLatest: number | null; max: number | null; sections: React.ReactNode; base: string;
}) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="ov-result" className={cn(CARD, "space-y-3")}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id="ov-result" className={BLOCK_TITLE}>{t("course.overview.latestResult")}</h2>
        <BlockLink href={`${base}/analytics`}>{t("course.overview.allResults")}</BlockLink>
      </div>
      {prepLatest !== null && (
        <p className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-[2rem] font-bold leading-9 tabular-nums text-slate-900">{prepLatest}</span>
          {max !== null && <span className="text-sm font-medium text-slate-700">{t("examPrep.goal.outOf", { max })}</span>}
        </p>
      )}
      {sections}
    </section>
  );
}

/** Other courses: the latest released grade with its feedback line. */
function GradeResult({ grade, base }: { grade: MyGradeOut; base: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const gradeText = useGradeListText();
  return (
    <section aria-labelledby="ov-result" className={cn(CARD, "space-y-2")}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id="ov-result" className={BLOCK_TITLE}>{t("course.overview.latestResult")}</h2>
        <BlockLink href={`${base}/analytics#grades`}>{t("course.overview.allGrades")}</BlockLink>
      </div>
      <p className="break-words text-base font-semibold leading-6 text-slate-900">{pickLocalized(grade.title, lang, course.default_language) || t("assessments.untitled")}</p>
      <p className="text-2xl font-bold leading-8 tabular-nums text-slate-900">{gradeText(grade) || "—"}</p>
      {grade.feedback_text && <p className="line-clamp-2 break-words text-sm leading-5 text-slate-700">«{grade.feedback_text}»</p>}
      {grade.released_at && <p className="text-sm leading-5 text-slate-600">{fmtShortDateTime(grade.released_at, lang)}</p>}
      {grade.kept_attempt_id && (
        <div><LinkButton variant="secondary" href={`${base}/attempts/${grade.kept_attempt_id}/result`}>{t("home.action.result")}</LinkButton></div>
      )}
    </section>
  );
}

function AnnouncementStrip({ base }: { base: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const [row, setRow] = useState<AnnouncementStudentOut | null | undefined>(undefined);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    listAnnouncements(course.id, { limit: 1 }).then(
      (p) => { if (alive) setRow((p.items[0] as AnnouncementStudentOut | undefined) ?? null); },
      () => { if (alive) setFailed(true); },
    );
    return () => { alive = false; };
  }, [course.id]);
  if (failed || row === null) return null;
  if (row === undefined) return <BlockSkeleton title={t("course.overview.announcements")} />;
  const text = excerptText(row.body_html.replace(/<[^>]*>/g, " "), 180);
  return (
    <section aria-labelledby="ov-ann" className={cn(CARD, "space-y-2")}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id="ov-ann" className={cn(BLOCK_TITLE, "inline-flex items-center gap-2")}><Megaphone aria-hidden="true" className="h-4 w-4" />{t("course.overview.announcements")}</h2>
        <BlockLink href={`${base}/announcements`}>{t("course.overview.allAnnouncements")}</BlockLink>
      </div>
      <p className="break-words text-base font-semibold leading-6 text-slate-900">{row.title}</p>
      <p className="text-sm leading-5 text-slate-600">{fmtShortDateTime(row.published_at, lang)}</p>
      {text && <p className="line-clamp-2 break-words text-sm leading-5 text-slate-700">{text}</p>}
    </section>
  );
}

/** «Уроки»: the next lesson and «Все уроки» (only when the course has lessons). */
function LessonsTeaser({ next, done, total, base }: { next: LessonRef | null; done: number; total: number; base: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  return (
    <section aria-labelledby="ov-lessons" className={cn(CARD, "space-y-2")}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id="ov-lessons" className={BLOCK_TITLE}>{t("course.tabs.lessons")}</h2>
        <BlockLink href={`${base}/lessons`}>{t("course.overview.allLessons")}</BlockLink>
      </div>
      {next ? (
        <Link href={lessonHref(base, next)}
          className={cn("flex min-h-11 items-center gap-3 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 hover:border-brand-200 hover:bg-brand-50", focusRing)}>
          <span aria-hidden="true" className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-brand-700">
            {next.item.kind === "url" ? <PlayCircle className="h-4 w-4" /> : <ItemKindIcon kind={next.item.kind} assignmentKind={next.item.link?.assignment_kind} />}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-xs font-medium leading-4 text-brand-700">{t("course.overview.continueLesson")}</span>
            <span className="block break-words text-sm font-semibold leading-5 text-slate-900">
              {pickLocalized(next.item.title, lang, course.default_language) || t("courses.list.untitled")}
            </span>
          </span>
          <ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-400" />
        </Link>
      ) : null}
      {total > 0 && <p className="text-sm leading-5 text-slate-600">{t("course.header.progress", { done, total })}</p>}
    </section>
  );
}

function AboutCard({ exam, counts, testsCount }: { exam: boolean; counts: { modules: number; lessons: number } | null; testsCount: number | null }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const base = `/${lang}/courses/${course.id}`;
  const description = course.description ? pickLocalized(course.description, lang, course.default_language) : "";
  const platform = !!course.is_platform_course;
  // D10: the teachers' display names (platform courses: who runs them, as before: no names)
  const [teachers, setTeachers] = useState<string[] | null>(platform ? [] : null);
  useEffect(() => {
    if (platform) return;
    let alive = true;
    listPeople(course.id, { limit: 20 }).then(
      (p) => {
        if (!alive) return;
        const names = (p.items as StaffPublicOut[]).filter((r) => r.role === "teacher" && r.display_name).map((r) => r.display_name);
        setTeachers(names);
      },
      () => { if (alive) setTeachers([]); },
    );
    return () => { alive = false; };
  }, [course.id, platform]);
  const lessonRows = useLessonCourseRows(exam ? course.id : null);
  // the labels are core keys (no staff dictionary on a student page); rows keyed by position
  const rows: [string, React.ReactNode][] = [
    [platform ? t("courses.home.provider") : t("course.overview.teachers"),
      platform ? t("courses.home.providerPlatform")
        : teachers === null ? <Skeleton className="h-5 w-24" />
          : teachers.length > 0 ? teachers.join(", ") : course.owner_display_name || "—"],
    [t("courses.home.languages"), course.languages.map((l) => t(`courses.languages.${l}`)).join(", ")],
    ...(counts && counts.modules > 0 ? [[t("course.overview.modules"), String(counts.modules)] as [string, React.ReactNode]] : []),
    ...(counts && counts.lessons > 0 ? [[t("course.overview.lessons"), String(counts.lessons)] as [string, React.ReactNode]] : []),
    ...(testsCount ? [[t("course.overview.tests"), String(testsCount)] as [string, React.ReactNode]] : []),
  ];
  const lessonCourses = (lessonRows ?? []).slice(0, 3);
  return (
    <section aria-labelledby="ov-about" className={cn(CARD, "space-y-3")}>
      <div className="flex items-start justify-between gap-3">
        <h2 id="ov-about" className="text-base font-semibold leading-6 text-slate-900">{t("course.overview.about")}</h2>
        <Mascot pose="reading" size={56} className="hidden shrink-0 lg:block" />
      </div>
      {description && <p className="line-clamp-6 whitespace-pre-line break-words text-sm leading-6 text-slate-700">{description}</p>}
      <dl className="divide-y divide-slate-100">
        {rows.map(([k, v], i) => (
          <div key={i} className="flex items-baseline justify-between gap-3 py-2">
            <dt className="text-sm leading-5 text-slate-600">{k}</dt>
            <dd className="min-w-0 break-words text-right text-sm font-semibold leading-5 text-slate-900">{v}</dd>
          </div>
        ))}
      </dl>
      {course.features?.files && (
        <Link href={`${base}/files`} className={cn("flex min-h-11 items-center gap-2 rounded-xl border border-slate-200 px-3 text-sm font-semibold text-slate-800 hover:bg-slate-50", focusRing)}>
          <FolderOpen aria-hidden="true" className="h-4 w-4 text-brand-700" />
          <span className="flex-1">{t("course.overview.materials")}</span>
          <ChevronRight aria-hidden="true" className="h-4 w-4 text-slate-400" />
        </Link>
      )}
      {lessonCourses.length > 0 && (
        <div className="space-y-2 border-t border-slate-100 pt-3">
          <h3 className="text-sm font-semibold leading-5 text-slate-900">{t("course.overview.lessonCourses")}</h3>
          <ul className="space-y-1">
            {lessonCourses.map((r) => (
              <li key={r.id}>
                <Link href={r.enrolled || r.is_staff ? `/${lang}/courses/${r.id}` : `/${lang}/courses/catalog/${r.id}`}
                  className={cn("flex min-h-11 items-center gap-2 rounded-lg px-2 text-sm text-slate-800 hover:bg-slate-50", focusRing)}>
                  <span className="min-w-0 flex-1 break-words font-medium">{pickLocalized(r.title, lang) || t("courses.list.untitled")}</span>
                  {r.enrolled && r.progress && r.progress.total > 0 && (
                    <span className="shrink-0 text-xs tabular-nums text-slate-600">{t("course.overview.ofTotal", { done: r.progress.done, total: r.progress.total })}</span>
                  )}
                </Link>
              </li>
            ))}
          </ul>
          <BlockLink href={`${base}/lessons`}>{t("course.overview.allLessonCourses")}</BlockLink>
        </div>
      )}
    </section>
  );
}

/** Other courses: the running quiz, else the next lesson, else the next assignment to start or hand in. */
function useNextAssignment(enabled: boolean) {
  const { course } = useCourse();
  const [items, setItems] = useState<AssignmentStudentOut[] | null>(enabled ? null : []);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => {
    if (!enabled) return;
    setError(null);
    try {
      setItems((await listAssignments(course.id, { limit: 50 })).items as AssignmentStudentOut[]);
    } catch (e) {
      setError(e);
    }
  }, [course.id, enabled]);
  useEffect(() => { void load(); }, [load]);
  const next = useMemo(() => {
    if (!items) return null;
    const now = Date.now();
    const rows = sortForStudent(items).map((a) => ({ a, v: studentAssignmentView(a, now, false) }));
    const id = primaryAssignmentId(rows);
    return rows.find((r) => r.a.id === id) ?? null;
  }, [items]);
  return { items, next, error, retry: load };
}

function useLatestGrade() {
  const { course } = useCourse();
  const [grades, setGrades] = useState<MyGradeOut[] | null>(null);
  useEffect(() => {
    let alive = true;
    getMyGrades(course.id).then((r) => { if (alive) setGrades(r.items ?? []); }, () => { if (alive) setGrades([]); });
    return () => { alive = false; };
  }, [course.id]);
  return useMemo(() => {
    const graded = (grades ?? []).filter((g) => g.state === "graded");
    if (graded.length === 0) return null;
    const ts = (g: MyGradeOut) => parseApiDate(g.released_at ?? null)?.getTime() ?? 0;
    return graded.reduce((best, g) => (ts(g) > ts(best) ? g : best));
  }, [grades]);
}

function ExamOverview({ lessons, lessonData }: { lessons: LessonRef[]; lessonData: ReturnType<typeof useStudentModules>["data"] }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const errorText = useErrorText();
  const base = `/${lang}/courses/${course.id}`;
  const { data: prep, error, refresh } = useExamPrep(course.id);
  useEffect(() => { if (prep) noteExamPrep(course.id, prep); }, [course.id, prep]); // the getting-started checklist
  const next = lessonData ? nextOpen(lessons, lessonData.up_next) : null;
  const done = lessons.filter((l) => isDone(l.item)).length;
  const hasResult = !!prep && (!!prep.latest || prep.history.length > 0);
  const main = (
    <div className="min-w-0 space-y-4 lg:space-y-5">
      {error && !prep ? <ErrorState message={errorText(error)} onRetry={() => void refresh()} />
        : !prep ? <BlockSkeleton title={t("examPrep.next.title")} />
          : prep.next ? <NextCard next={prep.next} courseId={course.id} className="rounded-card shadow-none" /> : null}
      {prep && hasResult && (
        <ExamResult base={base} prepLatest={wholeNumber(prep.latest?.value)} max={wholeNumber(prep.goal.scale_max)}
          sections={prep.sections.length > 0 ? <SectionBars data={prep} className="border-0 p-0 shadow-none" /> : null} />
      )}
      {course.features?.announcements && <AnnouncementStrip base={base} />}
      {lessons.length > 0 && <LessonsTeaser next={next} done={done} total={lessons.length} base={base} />}
      {prep?.needs_pass && <UnlockCard />}
    </div>
  );
  const counts = lessonData ? { modules: lessonData.modules.length, lessons: lessons.filter((l) => LESSON_KINDS.has(l.item.kind)).length } : null;
  return <Columns main={main} side={<AboutCard exam counts={counts} testsCount={prep?.library_total ?? null} />} />;
}

function GeneralOverview({ lessons, lessonData }: { lessons: LessonRef[]; lessonData: ReturnType<typeof useStudentModules>["data"] }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const errorText = useErrorText();
  const base = `/${lang}/courses/${course.id}`;
  const f = course.features;
  const hasWork = !f || !!f.tests || !!f.hand_ins;
  const { items, next: nextA, error, retry } = useNextAssignment(hasWork);
  const grade = useLatestGrade();
  const nextL = lessonData ? nextOpen(lessons, lessonData.up_next) : null;
  const done = lessons.filter((l) => isDone(l.item)).length;
  const lessonsLoading = !!f?.modules && !lessonData;
  // the running quiz first, then the next lesson, then the next assignment
  let step: React.ReactNode = null;
  if (error && !items) step = <ErrorState variant="inline" message={errorText(error)} onRetry={() => void retry()} />;
  else if (!items || lessonsLoading) step = <BlockSkeleton title={t("course.overview.nextStep")} />;
  else if (nextA && nextA.v.action === "continue") step = <AssignmentStep base={base} row={nextA} />;
  else if (nextL && !isLocked(nextL.mod, nextL.item)) step = <LessonStep base={base} next={nextL} started={done > 0} />;
  else if (nextA) step = <AssignmentStep base={base} row={nextA} />;
  const locked = !!lessonData?.modules.some((m) => m.access_locked);
  const main = (
    <div className="min-w-0 space-y-4 lg:space-y-5">
      {course.home_kind === "page" && course.home_page_id && <PageView pageId={course.home_page_id} embedded />}
      {course.status === "concluded" && (
        <p role="status" className="rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-base leading-6 text-slate-700 sm:text-sm">{t("courses.home.concludedNotice")}</p>
      )}
      {step}
      {grade && <GradeResult grade={grade} base={base} />}
      {f?.announcements && <AnnouncementStrip base={base} />}
      {lessons.length > 0 && <LessonsTeaser next={nextL} done={done} total={lessons.length} base={base} />}
      {locked && <UnlockCard />}
    </div>
  );
  const counts = lessonData ? { modules: lessonData.modules.length, lessons: lessons.filter((l) => LESSON_KINDS.has(l.item.kind)).length } : null;
  const testsCount = items ? items.filter((a) => a.kind === "quiz").length : null;
  return <Columns main={main} side={<AboutCard exam={false} counts={counts} testsCount={testsCount} />} />;
}

function AssignmentStep({ base, row }: { base: string; row: { a: AssignmentStudentOut; v: ReturnType<typeof studentAssignmentView> } }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  return (
    <section aria-labelledby="ov-next" className="space-y-2">
      <h2 id="ov-next" className={BLOCK_TITLE}>{t("course.overview.nextStep")}</h2>
      <StudentAssignmentCard as="div" a={row.a} v={row.v} base={base} primary
        title={pickLocalized(row.a.title, lang, course.default_language) || t("assignments.untitled")} />
    </section>
  );
}

function LessonStep({ base, next, started }: { base: string; next: LessonRef; started: boolean }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const title = pickLocalized(next.item.title, lang, course.default_language) || t("courses.list.untitled");
  const mod = pickLocalized(next.mod.title, lang, course.default_language);
  return (
    <section aria-labelledby="ov-next"
      className="flex flex-col gap-4 rounded-card border border-brand-200 bg-brand-50 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
      <div className="min-w-0">
        <h2 id="ov-next" className="text-sm font-semibold uppercase leading-5 tracking-wide text-brand-800">{t("course.overview.nextStep")}</h2>
        <p className="mt-1 break-words text-xl font-bold leading-7 text-slate-900">{title}</p>
        {mod && <p className="mt-1 break-words text-sm leading-5 text-slate-700">{mod}</p>}
      </div>
      <LinkButton href={lessonHref(base, next)} size="lg" rightIcon={<ArrowRight aria-hidden="true" className="h-5 w-5" />} className="w-full shrink-0 sm:w-auto">
        {started ? t("course.overview.continueLesson") : t("course.overview.startLesson")}
      </LinkButton>
    </section>
  );
}

function Columns({ main, side }: { main: React.ReactNode; side: React.ReactNode }) {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start lg:gap-6">
        {main}
        <aside className="min-w-0">{side}</aside>
      </div>
      <LeaveCourseLink />
    </div>
  );
}

/** `/courses/{c}` for a student of the course (Student view too). */
export function CourseOverview() {
  const { course } = useCourse();
  const { data: lessonData } = useStudentModules(course.id, !!course.features?.modules);
  const lessons = useMemo(() => lessonList(lessonData?.modules ?? []), [lessonData]);
  return isExamCourse(course)
    ? <ExamOverview lessons={lessons} lessonData={lessonData} />
    : <GeneralOverview lessons={lessons} lessonData={lessonData} />;
}
