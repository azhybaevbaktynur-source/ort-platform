"use client";

// Student UI U7 (docs/phases/STUDENT_UI_DESIGN.md §3.5) + F5b (COURSE_LESSONS_DESIGN L1, 7.1): `/courses/{c}/modules`
// for a student is the **course overview**, exam-prep and teacher courses alike: the cover banner (`CourseCover` until
// problem 7 stores a real cover) with the one primary action ("Начать курс" / "Продолжить курс" from the server's
// `up_next`; "Открыть доступ" in gold when only Pro lessons remain; "Повторить с начала" when everything is done),
// "Пройдено N из M" with the total duration, the syllabus by modules (`details`-like groups, the current one open;
// rows: done ✓ / open ○ / next ● / locked 🔒, kind icon and duration or "тест") and the About card (description,
// language, counts). A Pro module the student cannot open shows the gold "Pro" chip and the unlock pill; its rows
// carry titles and durations only (the server sends no destination). Facts: a plain link records its view on the
// click; lessons record theirs on the lesson page (video on play, page on open, file on download).
import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, ChevronDown, Circle, CircleDot, Lock, PartyPopper, PlayCircle, RotateCcw } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { getModules, recordView, setDone } from "@/lib/lms/modules";
import { templateUi } from "@/lib/lms/templates";
import { isStaffModules, type ItemStudentOut, type ModuleStudentOut, type ModulesStudentOut } from "@/lib/lms/modulesTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { CourseCover } from "@/components/lms/course/CourseCover";
import { fmtDayMonthTime } from "@/components/lms/home/format";
import { LeaveCourseLink } from "@/components/lms/home/LeaveCourseLink";
import { Checkbox, EmptyState, ErrorState, GoldPill, LinkButton, LoadingState, Mascot, cn, focusRing } from "@/components/ui";
import { STUDENT_SUBTITLE, STUDENT_TITLE } from "@/components/lms/student/StudentPageHeader";
import { ExternalIcon, ItemKindIcon, ModuleStateBadge, useItemKindText, useLockReasonText, useModuleErrorText, useRequirementText } from "./moduleUi";
import {
  courseProgress, formatDuration, isAccessLocked, isDone, isExempt, isLocked, lessonHref, lessonList, nextOpen, overviewState, type LessonRef,
} from "./lessons";
import { rememberLessonModules } from "./lessonNav";
import { ProChip } from "./ProLockCard";

const LESSON_KINDS = new Set(["page", "file", "url"]);

interface RowCtx {
  base: string;
  courseId: string;
  student: boolean;
  nextId: string | null;
  onFact: (moduleId: string, next: ModuleStudentOut) => void;
  onError: (e: unknown) => void;
}

/** Opening a test from the course path is its view fact (a `view` requirement on a test, the module's "started"), as
 * the 8a list did; lessons record theirs on the lesson page. Fire and forget: the lobby must not wait for it. */
export function viewOnOpen(courseId: string, ref: LessonRef, enabled: boolean): (() => void) | undefined {
  if (!enabled || ref.item.kind !== "assignment" || isLocked(ref.mod, ref.item)) return undefined;
  return () => { recordView(courseId, ref.mod.id, ref.item.id).catch(() => undefined); };
}

/** ✓ done, 🔒 locked, ● the next step, ○ otherwise (the status in words for screen readers). */
export function StatusIcon({ locked, done, current = false }: { locked: boolean; done: boolean; current?: boolean }) {
  const { t } = useTranslation();
  const icon = done
    ? <CheckCircle2 aria-hidden="true" className="h-5 w-5 shrink-0 text-success-700" />
    : locked
      ? <Lock aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-400" />
      : current
        ? <CircleDot aria-hidden="true" className="h-5 w-5 shrink-0 text-brand-600" />
        : <Circle aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-300" />;
  const word = done ? "done" : locked ? "locked" : "open";
  return <span className="inline-flex shrink-0">{icon}<span className="sr-only">{t(`modules.syllabus.status.${word}`)}</span></span>;
}

/** The kind of a row as icon + duration ("▶ 6 мин"), or icon + "Тест" for an assignment; the kind in words for
 * screen readers when the duration stands alone. */
export function KindMeta({ item, locked, className }: { item: ItemStudentOut; locked: boolean; className?: string }) {
  const { t } = useTranslation();
  const kindText = useItemKindText();
  const video = item.kind === "url" && !!item.video;
  const kind = video ? t("modules.syllabus.video") : kindText(item.kind, item.link?.assignment_kind ?? null);
  const duration = formatDuration(item.duration_s, t);
  // a locked url row carries no `video` (the server strips it), so its kind is unknown: a Pro row (and a locked url
  // row) shows the duration only, never a guessed "Ссылка"
  if (isAccessLocked(item) || (locked && item.kind === "url")) {
    return duration
      ? <span className={cn("inline-flex shrink-0 whitespace-nowrap text-sm leading-5 tabular-nums text-slate-600", className)}>{duration}</span>
      : null;
  }
  const icon = video
    ? <PlayCircle aria-hidden="true" className={cn("h-4 w-4 shrink-0", locked ? "text-slate-400" : "text-brand-600")} />
    : <ItemKindIcon kind={item.kind} assignmentKind={item.link?.assignment_kind ?? null} className={cn("h-4 w-4", locked ? "text-slate-400" : "text-slate-500")} />;
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-sm leading-5 text-slate-600", className)}>
      {icon}
      {duration ? <><span className="sr-only">{kind}, </span><span className="tabular-nums">{duration}</span></> : <span>{kind}</span>}
    </span>
  );
}

function SyllabusRow({ lesson, ctx }: { lesson: LessonRef; ctx: RowCtx }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const reqText = useRequirementText();
  const [busy, setBusy] = useState(false);
  const { mod, item } = lesson;
  const title = pickLocalized(item.title, lang, course.default_language) || t("modules.untitledItem");
  const locked = isLocked(mod, item);
  const exempt = isExempt(mod, item);
  const done = isDone(item);
  const current = !locked && !done && item.id === ctx.nextId;
  const req = item.requirement;
  const met = !!req?.met;

  const record = async () => {
    if (!ctx.student || locked) return;
    try {
      ctx.onFact(mod.id, await recordView(ctx.courseId, mod.id, item.id));
    } catch {
      // the view is a convenience fact; opening the target must not wait for it or fail because of it
    }
  };
  const toggleDone = async (value: boolean) => {
    setBusy(true);
    try {
      ctx.onFact(mod.id, await setDone(ctx.courseId, mod.id, item.id, value));
    } catch (e) {
      ctx.onError(e);
    } finally {
      setBusy(false);
    }
  };

  // the line under the title only when it says something beyond the kind (dates, requirements, why it waits)
  const metaParts: React.ReactNode[] = [];
  if (item.due_at) metaParts.push(<span key="due">{t("home.todo.due", { date: fmtDayMonthTime(item.due_at, lang) })}</span>);
  if (req && req.type !== "mark_done") metaParts.push(<span key="req" className={cn(met && "text-success-800")}>{reqText(req.type, req.threshold)}</span>);
  if (req && req.best_score_percent !== null && req.best_score_percent !== undefined && !met) {
    metaParts.push(<span key="best">{t("modules.req.best", { percent: Math.round(req.best_score_percent) })}</span>);
  }
  if (locked && mod.state !== "locked" && !isAccessLocked(item)) metaParts.push(<span key="seq" className="text-slate-700">{t("modules.reason.sequentialItem")}</span>);
  if (exempt) metaParts.push(<span key="ex">{t("modules.availableInAssignments")}</span>);
  const meta = metaParts.length > 0
    ? <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm leading-5 text-slate-600">{metaParts}</span>
    : null;

  const titleEl = <span className="line-clamp-2 break-words text-base font-medium leading-6 sm:text-[15px] sm:leading-5">{title}</span>;
  const rowCls = cn("flex min-h-12 w-full items-center gap-3 px-4 py-2.5 text-left sm:px-5", focusRing, "focus-visible:ring-inset focus-visible:ring-offset-0");
  const open = "text-slate-900 hover:bg-slate-50";
  const liCls = cn(current && "bg-brand-50/60");
  const inner = (titleNode: React.ReactNode = titleEl) => (
    <>
      <StatusIcon locked={locked} done={done} current={current} />
      <span className="min-w-0 flex-1">{titleNode}{meta}</span>
      <KindMeta item={item} locked={locked} />
    </>
  );

  let body: React.ReactNode;
  if (locked) {
    body = <div className={cn(rowCls, "text-slate-500")} aria-disabled="true">{inner()}</div>;
  } else if (item.kind === "url" && !item.video && item.link?.url) {
    // a plain link opens the stored address in a new tab (the click is its view)
    body = (
      <a href={item.link.url} target="_blank" rel="noopener noreferrer" onClick={() => void record()} className={cn(rowCls, open)}>
        {inner(<span className="flex items-center gap-1.5">{titleEl}<ExternalIcon /><span className="sr-only">{t("modules.opensNewTab")}</span></span>)}
      </a>
    );
  } else if (LESSON_KINDS.has(item.kind) || (item.kind === "assignment" && item.link)) {
    body = (
      <Link href={lessonHref(ctx.base, lesson)} onClick={viewOnOpen(ctx.courseId, lesson, ctx.student)} aria-current={current ? "step" : undefined}
        className={cn(rowCls, open)}>
        {inner()}
      </Link>
    );
  } else {
    body = <div className={cn(rowCls, "text-slate-900")}>{inner()}</div>;
  }

  if (req?.type !== "mark_done") return <li className={liCls}>{body}</li>;
  return (
    <li className={cn("sm:flex sm:items-center", liCls)}>
      <div className="min-w-0 sm:flex-1">{body}</div>
      <div className="shrink-0 pb-2 pl-12 pr-4 sm:pb-0 sm:pl-0 sm:pr-5">
        {ctx.student && !locked ? (
          <Checkbox label={t("modules.markDone")} checked={met} disabled={busy} onChange={(e) => void toggleDone(e.target.checked)} />
        ) : (
          <span className={cn("inline-flex min-h-8 items-center gap-1 text-sm", met ? "text-success-800" : "text-slate-600")}>
            {met ? t("modules.req.markedDone") : t("modules.req.mark_done")}
          </span>
        )}
      </div>
    </li>
  );
}

function ModuleSection({ mod, number, lessons, open, onToggle, ctx }: {
  mod: ModuleStudentOut;
  number: number;
  lessons: LessonRef[];
  open: boolean;
  onToggle: () => void;
  ctx: RowCtx;
}) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const reasonText = useLockReasonText();
  const listId = useId();
  const title = pickLocalized(mod.title, lang, course.default_language) || t("modules.untitledModule");
  const total = mod.total ?? lessons.length;
  const done = mod.done ?? lessons.filter((l) => isDone(l.item)).length;
  const duration = formatDuration(mod.duration_s ?? lessons.reduce((a, l) => a + (l.item.duration_s ?? 0), 0), t);
  const hasReq = mod.items.some((i) => i.requirement);
  const pro = !!mod.access_locked;
  const headingId = `module-${mod.id}-title`;
  return (
    <section id={`module-${mod.id}`} aria-labelledby={headingId} className="scroll-mt-20 overflow-hidden rounded-card border border-slate-200 bg-white">
      <header className="flex flex-wrap items-start gap-x-3 gap-y-1 px-4 py-3 sm:px-5">
        <h3 id={headingId} className="min-w-0 flex-1 basis-48">
          <button type="button" onClick={onToggle} aria-expanded={open} aria-controls={listId}
            className={cn("flex min-h-11 w-full items-center gap-2 rounded-control text-left text-base font-semibold leading-6 text-slate-900", focusRing, "focus-visible:ring-offset-0")}>
            <ChevronDown aria-hidden="true" className={cn("h-5 w-5 shrink-0 text-slate-500 transition-transform", !open && "-rotate-90")} />
            <span aria-hidden="true" className="w-5 shrink-0 text-center tabular-nums text-slate-500">{number}</span>
            <span className="min-w-0 break-words">{title}</span>
          </button>
        </h3>
        <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 pl-14 sm:min-h-11 sm:pl-0">
          {pro && <ProChip />}
          {total > 0 && (
            <span className="text-sm leading-6 text-slate-600">
              <span className="tabular-nums">{t("modules.overview.moduleDone", { done, total })}</span>
              {duration && <> · <span className="tabular-nums">{duration}</span></>}
            </span>
          )}
          {mod.state && (mod.state === "locked" || hasReq) && <ModuleStateBadge state={mod.state} />}
        </div>
      </header>
      {mod.state === "locked" && mod.lock_reasons.length > 0 && (
        <ul className="space-y-1 border-t border-slate-100 px-4 py-2 text-sm leading-6 text-slate-700 sm:px-5">
          {mod.lock_reasons.map((r, i) => (
            <li key={i} className="flex items-start gap-2"><Lock aria-hidden="true" className="mt-1 h-4 w-4 shrink-0" /><span className="break-words">{reasonText(r, course.default_language)}</span></li>
          ))}
        </ul>
      )}
      {pro && (
        <div className="flex flex-col gap-3 border-t border-slate-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <p className="text-sm leading-5 text-slate-700">{t("modules.overview.proModuleBody")}</p>
          <GoldPill href={`/${lang}/unlock`} icon={<Lock />} className="justify-center sm:shrink-0">{t("modules.overview.unlock")}</GoldPill>
        </div>
      )}
      <div id={listId} hidden={!open}>
        {lessons.length === 0 ? (
          <p className="border-t border-slate-100 px-4 py-3 text-base leading-6 text-slate-600 sm:px-5 sm:text-sm">{t("modules.noItemsStudent")}</p>
        ) : (
          <ul className="divide-y divide-slate-100 border-t border-slate-100">
            {lessons.map((l) => <SyllabusRow key={l.item.id} lesson={l} ctx={ctx} />)}
          </ul>
        )}
      </div>
    </section>
  );
}

/** The banner: cover, the course (exam-prep: its h1) and the one primary action; under it "Пройдено N из M". */
function Hero({ lessons, data, base, examPrep, track }: {
  lessons: LessonRef[]; data: ModulesStudentOut; base: string; examPrep: boolean; track: boolean;
}) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const courseTitle = pickLocalized(course.title, lang, course.default_language);
  const { done, total, duration_s } = courseProgress(data, lessons);
  const started = done > 0;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const countText = t("modules.syllabus.doneCount", { done, total });
  const duration = formatDuration(duration_s, t);

  // one state: its title, at most one line under it (never an empty one) and at most one action
  const st = overviewState(lessons, data.up_next);
  let title: string;
  let line: string | null = null;
  let action: React.ReactNode = null;
  if (st.kind === "next") {
    const nextTitle = pickLocalized(st.next.item.title, lang, course.default_language) || t("modules.untitledItem");
    title = started ? t("modules.syllabus.continueTitle") : t("modules.syllabus.readyTitle");
    line = t("modules.overview.nextUp", { title: nextTitle });
    action = (
      <LinkButton href={lessonHref(base, st.next)} onClick={viewOnOpen(course.id, st.next, track)} rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />} className="w-full shrink-0 sm:w-auto">
        {started ? t("modules.syllabus.continue") : t("modules.syllabus.start")}
      </LinkButton>
    );
  } else if (st.kind === "pro") {
    title = t("modules.overview.proLeft");
    action = <GoldPill href={`/${lang}/unlock`} icon={<Lock />} className="w-full justify-center sm:w-auto sm:shrink-0">{t("modules.overview.unlock")}</GoldPill>;
  } else if (st.kind === "later") {
    title = t("modules.overview.later");
  } else if (st.kind === "finished") {
    title = t("modules.overview.completed");
    line = t("modules.syllabus.doneBody");
    action = (
      <LinkButton href={lessonHref(base, lessons[0])} variant="secondary" leftIcon={<RotateCcw aria-hidden="true" className="h-4 w-4" />} className="w-full shrink-0 sm:w-auto">
        {t("modules.overview.restart")}
      </LinkButton>
    );
  } else {
    title = t("modules.overview.emptyTitle");
    line = t("modules.overview.emptyBody");
  }
  // exam-prep: the course is the h1, so the state is the line under it (the next lesson while there is one)
  const examLine = st.kind === "next" ? line : title;

  return (
    <section aria-labelledby="course-overview-title" className="overflow-hidden rounded-card border border-slate-200 bg-white">
      <CourseCover title={courseTitle} className="aspect-[16/9] sm:aspect-[3/1] lg:aspect-[5/1]" />
      <div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
        <div className="min-w-0">
          {examPrep ? (
            <>
              <p className="text-sm font-medium leading-5 text-brand-700">{t("student.nav.lessons")}</p>
              <h1 id="course-overview-title" className={cn(STUDENT_TITLE, "mt-0.5")}>{courseTitle}</h1>
              {examLine && <p className={STUDENT_SUBTITLE}>{examLine}</p>}
            </>
          ) : (
            <>
              <h2 id="course-overview-title" className="break-words text-lg font-semibold leading-7 text-slate-900">{title}</h2>
              {line && <p className="mt-1 break-words text-base leading-6 text-slate-600 sm:text-sm sm:leading-5">{line}</p>}
            </>
          )}
        </div>
        {action}
      </div>
      {total > 0 && (
        <div className="border-t border-slate-100 px-4 py-4 sm:px-5">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm leading-5">
            <span className="font-medium tabular-nums text-slate-800">{countText}</span>
            <span className="text-slate-600">
              <span className="tabular-nums">{t("modules.syllabus.percent", { percent: pct })}</span>
              {duration && <> · <span className="tabular-nums">{t("modules.overview.approx", { duration })}</span></>}
            </span>
          </div>
          <div role="progressbar" aria-label={t("modules.syllabus.progressLabel")} aria-valuemin={0} aria-valuemax={total} aria-valuenow={done} aria-valuetext={countText}
            className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-brand-600 transition-[width]" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}
    </section>
  );
}

function AboutCard({ modules, lessons, durationS }: { modules: number; lessons: LessonRef[]; durationS: number }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const description = course.description ? pickLocalized(course.description, lang, course.default_language) : "";
  const lessonCount = lessons.filter((l) => LESSON_KINDS.has(l.item.kind)).length;
  const testCount = lessons.filter((l) => l.item.kind === "assignment").length;
  const duration = formatDuration(durationS, t);
  const rows: [string, string][] = [
    [t("modules.syllabus.aboutLanguage"), t(`pages.lang.${course.default_language}`)],
    [t("modules.syllabus.aboutModules"), String(modules)],
    [t("modules.syllabus.aboutLessons"), String(lessonCount)],
    ...(testCount > 0 ? [[t("modules.overview.aboutTests"), String(testCount)] as [string, string]] : []),
    ...(duration ? [[t("modules.overview.aboutDuration"), duration] as [string, string]] : []),
  ];
  return (
    <section aria-labelledby="course-about-title" className="rounded-card border border-slate-200 bg-white p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <h2 id="course-about-title" className="text-base font-semibold leading-6 text-slate-900">{t("modules.syllabus.aboutTitle")}</h2>
        <Mascot pose="reading" size={56} className="hidden shrink-0 lg:block" />
      </div>
      {description && <p className="mt-2 line-clamp-6 whitespace-pre-line break-words text-sm leading-6 text-slate-700">{description}</p>}
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3 lg:grid-cols-1 lg:gap-0 lg:divide-y lg:divide-slate-100">
        {rows.map(([k, v]) => (
          <div key={k} className="min-w-0 lg:flex lg:items-baseline lg:justify-between lg:gap-3 lg:py-2">
            <dt className="break-words text-xs leading-4 text-slate-600 lg:text-sm lg:leading-5">{k}</dt>
            <dd className="mt-0.5 break-words text-base font-semibold leading-6 text-slate-900 lg:mt-0 lg:text-right">{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function StudentSyllabus() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const errorText = useModuleErrorText();
  const [data, setData] = useState<ModulesStudentOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [rowError, setRowError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [celebrate, setCelebrate] = useState<string | null>(null);
  const [openIds, setOpenIds] = useState<Set<string> | null>(null);
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);
  const dataRef = useRef(data);
  dataRef.current = data;
  const base = `/${lang}/courses/${course.id}`;

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError(null);
    try {
      const out = await getModules(course.id);
      if (!mounted.current) return;
      const student: ModulesStudentOut = isStaffModules(out)
        ? { modules: [], up_next: null }
        : { modules: out.modules ?? [], up_next: out.up_next ?? null, progress: out.progress };
      setData(student);
      rememberLessonModules(course.id, student.modules);
    } catch (e) {
      if (mounted.current) setError(e);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [course.id]);
  useEffect(() => { void load(); }, [load]);

  // concluded courses refuse new facts (403): the list stays readable, links still open
  const readOnly = !!course.my_enrollment.read_only || course.status === "concluded";
  const lessons = useMemo(() => lessonList(data?.modules ?? []), [data]);
  const byModule = useMemo(() => {
    const map = new Map<string, LessonRef[]>();
    for (const l of lessons) map.set(l.mod.id, [...(map.get(l.mod.id) ?? []), l]);
    return map;
  }, [lessons]);
  const next = useMemo(() => (data ? nextOpen(lessons, data.up_next) : null), [data, lessons]);

  // the current module (the one holding "up next", else the first) opens; a sidebar / outline link `#module-{id}`
  // opens and scrolls to its module once the sections exist
  useEffect(() => {
    if (!data || openIds) return;
    const hash = window.location.hash;
    const fromHash = /^#module-[0-9a-f-]{36}$/.test(hash) ? hash.slice("#module-".length) : null;
    const first = fromHash ?? next?.mod.id ?? data.modules[0]?.id ?? null;
    setOpenIds(new Set(first ? [first] : []));
    if (fromHash) requestAnimationFrame(() => document.getElementById(`module-${fromHash}`)?.scrollIntoView());
  }, [data, next, openIds]);

  const ctx: RowCtx = {
    base,
    courseId: course.id,
    student: !readOnly,
    nextId: next?.item.id ?? null,
    onError: setRowError,
    onFact: (moduleId, updatedModule) => {
      setRowError(null);
      const cur = dataRef.current;
      if (!cur) return;
      const prev = cur.modules.find((m) => m.id === moduleId);
      if (prev && prev.state !== "completed" && updatedModule.state === "completed") {
        setCelebrate(pickLocalized(updatedModule.title, lang, course.default_language) || t("modules.untitledModule"));
      }
      const updated = { ...cur, modules: cur.modules.map((m) => (m.id === moduleId ? updatedModule : m)) };
      dataRef.current = updated;
      setData(updated);
      // the course bar and "up next" are the server's: refresh quietly (a completed module may also open later ones)
      void load(true);
    },
  };

  const examPrep = templateUi(course).studentLayout === "exam_prep";
  const early = error && !data
    ? <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />
    : !data
      ? <LoadingState rows={4} />
      : data.modules.length === 0
        ? <EmptyState mascot="reading" title={t("modules.emptyStudentTitle")} description={t("modules.emptyStudentBody")} />
        : null;
  // exam-prep courses: the course layout shows no course header here, the banner names the page
  if (early || !data) {
    return (
      <div className="flex w-full flex-col gap-4">
        {examPrep && (
          <header>
            <h1 className={STUDENT_TITLE}>{t("student.nav.lessons")}</h1>
            <p className={STUDENT_SUBTITLE}>{pickLocalized(course.title, lang, course.default_language)}</p>
          </header>
        )}
        {early}
      </div>
    );
  }
  const { duration_s } = courseProgress(data, lessons);
  const isOpen = (id: string) => openIds?.has(id) ?? false;
  return (
    <div className="flex w-full flex-col gap-4 lg:gap-6">
      <Hero lessons={lessons} data={data} base={base} examPrep={examPrep} track={!readOnly} />
      {course.status === "concluded" && (
        <p role="status" className="rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-base leading-6 text-slate-700 sm:text-sm">{t("courses.home.concludedNotice")}</p>
      )}
      <div aria-live="polite" className="empty:hidden">
        {celebrate && (
          <p className="flex items-start gap-2 rounded-xl border border-success-200 bg-success-50 px-4 py-3 text-base leading-6 text-success-900">
            <PartyPopper aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />{t("modules.celebrate", { title: celebrate })}
          </p>
        )}
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start lg:gap-6">
        {/* a plain block, not a <section>: each module is the section (tests and the sidebar read them by heading) */}
        <div className="min-w-0 space-y-3">
          <h2 className="text-lg font-semibold leading-7 text-slate-900">{t("modules.overview.syllabusTitle")}</h2>
          {rowError ? <ErrorState variant="inline" message={errorText(rowError)} /> : null}
          {data.modules.map((m, i) => (
            <ModuleSection key={m.id} mod={m} number={i + 1} lessons={byModule.get(m.id) ?? []} ctx={ctx} open={isOpen(m.id)}
              onToggle={() => setOpenIds((s) => {
                const n = new Set(s ?? []);
                if (n.has(m.id)) n.delete(m.id); else n.add(m.id);
                return n;
              })} />
          ))}
        </div>
        <aside className="min-w-0 lg:sticky lg:top-8">
          <AboutCard modules={data.modules.length} lessons={lessons} durationS={duration_s} />
        </aside>
      </div>
      {!readOnly && !examPrep && <LeaveCourseLink />}
    </div>
  );
}
