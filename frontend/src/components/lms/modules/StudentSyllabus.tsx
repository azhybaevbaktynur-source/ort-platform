"use client";

// Student UI U7 (docs/phases/STUDENT_UI_DESIGN.md §3.5): `/courses/{c}/modules` for a student, exam-prep and general
// courses alike: a "Ready to start?" card with the one primary action (start / continue the course) and the progress
// bar, the modules as collapsible sections (done ✓ / open ○ / locked 🔒 with the gating reason; ▶ for a video, the
// kind icon otherwise) and an "About the course" card (a side column from `lg`, under the start card on phones).
// Source: `GET /courses/{c}/modules` (evaluated by the server; locked rows carry no destination). A video row opens the
// lesson page; pages, files, assignments and plain links behave as in the modules list (view fact, download, new tab).
import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, ChevronDown, Circle, Lock, PartyPopper, PlayCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { getModules, recordView, setDone } from "@/lib/lms/modules";
import { downloadCourseFile } from "@/lib/lms/courseFiles";
import { templateUi } from "@/lib/lms/templates";
import { isStaffModules, type ItemStudentOut, type ModuleStudentOut, type ModulesStudentOut } from "@/lib/lms/modulesTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { fmtDayMonthTime } from "@/components/lms/home/format";
import { LeaveCourseLink } from "@/components/lms/home/LeaveCourseLink";
import { Checkbox, EmptyState, ErrorState, LinkButton, LoadingState, Mascot, cn, focusRing } from "@/components/ui";
import { ExternalIcon, ItemKindIcon, ModuleStateBadge, useItemKindText, useLockReasonText, useModuleErrorText, useRequirementText } from "./moduleUi";
import { isExempt, isLocked, lessonHref, lessonList, lessonRoute, nextLesson, syllabusProgress, type LessonRef } from "./lessons";
import { rememberLessonModules } from "./lessonNav";
import { StudentPageHeader } from "@/components/lms/student/StudentPageHeader";

interface RowCtx {
  base: string;
  courseId: string;
  student: boolean;
  onFact: (moduleId: string, next: ModuleStudentOut) => void;
  onError: (e: unknown) => void;
}

/** ✓ done, 🔒 locked, ○ otherwise (with the status in words for screen readers when it means something). */
function StatusIcon({ locked, met, hasReq }: { locked: boolean; met: boolean; hasReq: boolean }) {
  const { t } = useTranslation();
  const icon = locked
    ? <Lock aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-400" />
    : met
      ? <CheckCircle2 aria-hidden="true" className="h-5 w-5 shrink-0 text-success-700" />
      : <Circle aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-300" />;
  const word = locked ? "locked" : met ? "done" : hasReq ? "open" : null;
  return <span className="inline-flex shrink-0">{icon}{word && <span className="sr-only">{t(`modules.syllabus.status.${word}`)}</span>}</span>;
}

function SyllabusRow({ lesson, ctx }: { lesson: LessonRef; ctx: RowCtx }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const kindText = useItemKindText();
  const reqText = useRequirementText();
  const [busy, setBusy] = useState(false);
  const { mod, item } = lesson;
  const title = pickLocalized(item.title, lang, course.default_language) || t("modules.untitledItem");
  const locked = isLocked(mod, item);
  const exempt = isExempt(mod, item);
  const req = item.requirement;
  const met = !!req?.met;
  const assignmentKind = item.link?.assignment_kind ?? null;
  const video = !locked && item.kind === "url" && item.video ? item.video : null;

  const record = async () => {
    if (!ctx.student || locked) return;
    try {
      ctx.onFact(mod.id, await recordView(ctx.courseId, mod.id, item.id));
    } catch {
      // the view is a convenience fact; opening the target must not wait for it or fail because of it
    }
  };
  const toggleDone = async (done: boolean) => {
    setBusy(true);
    try {
      ctx.onFact(mod.id, await setDone(ctx.courseId, mod.id, item.id, done));
    } catch (e) {
      ctx.onError(e);
    } finally {
      setBusy(false);
    }
  };
  const openFile = async () => {
    if (!item.link?.file_id) return;
    setBusy(true);
    void record();
    try {
      await downloadCourseFile(ctx.courseId, item.link.file_id);
    } catch (e) {
      ctx.onError(e);
    } finally {
      setBusy(false);
    }
  };

  const canDownload = !locked && item.kind === "file" && !!item.link?.file_id;
  const meta = (
    <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm leading-5 text-slate-600 sm:text-xs">
      <span>{video ? t("modules.syllabus.video") : kindText(item.kind, assignmentKind)}</span>
      {item.due_at && <span>{t("home.todo.due", { date: fmtDayMonthTime(item.due_at, lang) })}</span>}
      {req && req.type !== "mark_done" && <span className={cn(met && "text-success-800")}>{reqText(req.type, req.threshold)}</span>}
      {req && req.best_score_percent !== null && req.best_score_percent !== undefined && !met && (
        <span>{t("modules.req.best", { percent: Math.round(req.best_score_percent) })}</span>
      )}
      {locked && mod.state !== "locked" && <span className="text-slate-700">{t("modules.reason.sequentialItem")}</span>}
      {exempt && <span>{t("modules.availableInAssignments")}</span>}
      {canDownload && <span className="font-semibold text-brand-700">{t("modules.download")}</span>}
    </span>
  );
  const titleEl = <span className="block break-words text-base font-medium leading-6 sm:text-[15px] sm:leading-5">{title}</span>;
  const rowCls = cn("flex min-h-12 w-full items-center gap-3 px-4 py-2.5 text-left sm:px-5", focusRing, "focus-visible:ring-inset focus-visible:ring-offset-0");
  const open = "text-slate-900 hover:bg-slate-50";
  const lead = <StatusIcon locked={locked} met={met} hasReq={!!req} />;
  const trail = video
    ? <PlayCircle aria-hidden="true" className="h-5 w-5 shrink-0 text-brand-600" />
    : <ItemKindIcon kind={item.kind} assignmentKind={assignmentKind} className={cn("h-5 w-5", locked ? "text-slate-300" : "text-slate-400")} />;
  const inner = (extra?: React.ReactNode) => <>{lead}<span className="min-w-0 flex-1">{extra ?? titleEl}{meta}</span>{trail}</>;

  let body: React.ReactNode;
  if (locked) {
    body = <div className={cn(rowCls, "text-slate-500")} aria-disabled="true">{inner()}</div>;
  } else if (video) {
    // the lesson page records the view itself
    body = <Link href={lessonRoute(ctx.base, mod.id, item.id)} className={cn(rowCls, open)}>{inner()}</Link>;
  } else if (item.kind === "url" && item.link?.url) {
    body = (
      <a href={item.link.url} target="_blank" rel="noopener noreferrer" onClick={() => void record()} className={cn(rowCls, open)}>
        {inner(<span className="flex items-center gap-1.5">{titleEl}<ExternalIcon /><span className="sr-only">{t("modules.opensNewTab")}</span></span>)}
      </a>
    );
  } else if (canDownload) {
    body = (
      <button type="button" onClick={() => void openFile()} disabled={busy} aria-busy={busy || undefined} className={cn(rowCls, open, "disabled:opacity-70")}>
        {inner()}
      </button>
    );
  } else if ((item.kind === "page" && item.link?.page_id) || (item.kind === "assignment" && item.link)) {
    const href = lessonHref(ctx.base, lesson);
    body = <Link href={href} onClick={() => void record()} className={cn(rowCls, open)}>{inner()}</Link>;
  } else {
    body = <div className={cn(rowCls, "text-slate-900")}>{inner()}</div>;
  }

  if (req?.type !== "mark_done") return <li>{body}</li>;
  return (
    <li className="sm:flex sm:items-center">
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

function ModuleSection({ mod, lessons, open, onToggle, ctx }: {
  mod: ModuleStudentOut;
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
  const withReq = mod.items.filter((i) => i.requirement);
  const done = withReq.filter((i) => i.requirement?.met).length;
  const count = lessons.length;
  const headingId = `module-${mod.id}-title`;
  return (
    <section id={`module-${mod.id}`} aria-labelledby={headingId} className="scroll-mt-20 overflow-hidden rounded-card border border-slate-200 bg-white">
      <header className="flex flex-wrap items-start gap-x-3 gap-y-1 px-4 py-3 sm:px-5">
        <h3 id={headingId} className="min-w-0 flex-1 basis-48">
          <button type="button" onClick={onToggle} aria-expanded={open} aria-controls={listId}
            className={cn("flex min-h-11 w-full items-center gap-2 rounded-control text-left text-base font-semibold leading-6 text-slate-900", focusRing, "focus-visible:ring-offset-0")}>
            <ChevronDown aria-hidden="true" className={cn("h-5 w-5 shrink-0 text-slate-500 transition-transform", !open && "-rotate-90")} />
            <span className="min-w-0 break-words">{title}</span>
          </button>
        </h3>
        <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 pl-7 sm:min-h-11 sm:pl-0">
          <span className="text-sm leading-6 text-slate-600">
            {t("modules.syllabus.lessonCount", { count })}
            {withReq.length > 0 && <> · {t("modules.syllabus.doneCountShort", { done, total: withReq.length })}</>}
          </span>
          {mod.state && (mod.state === "locked" || withReq.length > 0) && <ModuleStateBadge state={mod.state} />}
        </div>
      </header>
      {mod.state === "locked" && mod.lock_reasons.length > 0 && (
        <ul className="space-y-1 border-t border-slate-100 px-4 py-2 text-sm leading-6 text-slate-700 sm:px-5">
          {mod.lock_reasons.map((r, i) => (
            <li key={i} className="flex items-start gap-2"><Lock aria-hidden="true" className="mt-1 h-4 w-4 shrink-0" /><span className="break-words">{reasonText(r, course.default_language)}</span></li>
          ))}
        </ul>
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

function StartCard({ lessons, data, base }: { lessons: LessonRef[]; data: ModulesStudentOut; base: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const { done, total } = syllabusProgress(lessons);
  const next = nextLesson(lessons, data.up_next);
  const started = done > 0;
  const nextTitle = next ? pickLocalized(next.item.title, lang, course.default_language) || t("modules.untitledItem") : "";
  const finished = total > 0 && done >= total;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const countText = t("modules.syllabus.doneCount", { done, total });
  return (
    <div className="rounded-card border border-slate-200 bg-white p-4 sm:p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h2 className="break-words text-lg font-semibold leading-7 text-slate-900">
            {finished ? t("modules.syllabus.doneTitle") : started ? t("modules.syllabus.continueTitle") : t("modules.syllabus.readyTitle")}
          </h2>
          <p className="mt-1 break-words text-base leading-6 text-slate-600 sm:text-sm sm:leading-5">
            {finished
              ? t("modules.syllabus.doneBody")
              : next ? t(started ? "modules.syllabus.continueBody" : "modules.syllabus.readyBody", { title: nextTitle }) : null}
          </p>
        </div>
        {next && !finished && (
          <LinkButton href={lessonHref(base, next)} rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />} className="w-full shrink-0 sm:w-auto">
            {started ? t("modules.syllabus.continue") : t("modules.syllabus.start")}
          </LinkButton>
        )}
      </div>
      {total > 0 && (
        <div className="mt-4 border-t border-slate-100 pt-4">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm leading-5">
            <span className="font-medium text-slate-800">{t("modules.syllabus.progressLabel")}</span>
            <span className="text-slate-600"><span className="tabular-nums">{countText}</span> · <span className="tabular-nums">{t("modules.syllabus.percent", { percent: pct })}</span></span>
          </div>
          <div role="progressbar" aria-label={t("modules.syllabus.progressLabel")} aria-valuemin={0} aria-valuemax={total} aria-valuenow={done} aria-valuetext={countText}
            className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-brand-600 transition-[width]" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}
    </div>
  );
}

function AboutCard({ modules, lessons }: { modules: number; lessons: number }) {
  const { t } = useTranslation();
  const { course } = useCourse();
  const rows: [string, string][] = [
    [t("modules.syllabus.aboutModules"), String(modules)],
    [t("modules.syllabus.aboutLessons"), String(lessons)],
    [t("modules.syllabus.aboutLanguage"), t(`pages.lang.${course.default_language}`)],
  ];
  return (
    <div className="rounded-card border border-slate-200 bg-white p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-base font-semibold leading-6 text-slate-900">{t("modules.syllabus.aboutTitle")}</h2>
        <Mascot pose="reading" size={56} className="hidden shrink-0 lg:block" />
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-3 lg:grid-cols-1 lg:gap-0 lg:divide-y lg:divide-slate-100">
        {rows.map(([k, v]) => (
          <div key={k} className="min-w-0 lg:flex lg:items-baseline lg:justify-between lg:gap-3 lg:py-2">
            <dt className="break-words text-xs leading-4 text-slate-600 lg:text-sm lg:leading-5">{k}</dt>
            <dd className="mt-0.5 break-words text-base font-semibold leading-6 text-slate-900 lg:mt-0 lg:text-right">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** "Видеоуроки" with the course name under it (exam-prep courses, where the course header is not shown). */
function SyllabusTitle() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  return <StudentPageHeader title={t("student.nav.lessons")} subtitle={pickLocalized(course.title, lang, course.default_language)} />;
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
  const [closed, setClosed] = useState<Set<string>>(() => new Set());
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
      const student = isStaffModules(out) ? { modules: [], up_next: null } : { modules: out.modules ?? [], up_next: out.up_next ?? null };
      setData(student);
      rememberLessonModules(course.id, student.modules);
    } catch (e) {
      if (mounted.current) setError(e);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [course.id]);
  useEffect(() => { void load(); }, [load]);

  // a sidebar sub-link (`#module-{id}`) from another page: scroll once the sections exist
  const scrolled = useRef(false);
  useEffect(() => {
    if (!data || scrolled.current) return;
    scrolled.current = true;
    const hash = window.location.hash;
    if (/^#module-[0-9a-f-]{36}$/.test(hash)) document.getElementById(hash.slice(1))?.scrollIntoView();
  }, [data]);

  // concluded courses refuse new facts (403): the list stays readable, links still open
  const readOnly = !!course.my_enrollment.read_only || course.status === "concluded";
  const lessons = useMemo(() => lessonList(data?.modules ?? []), [data]);
  const byModule = useMemo(() => {
    const map = new Map<string, LessonRef[]>();
    for (const l of lessons) map.set(l.mod.id, [...(map.get(l.mod.id) ?? []), l]);
    return map;
  }, [lessons]);

  const ctx: RowCtx = {
    base,
    courseId: course.id,
    student: !readOnly,
    onError: setRowError,
    onFact: (moduleId, next) => {
      setRowError(null);
      const cur = dataRef.current;
      if (!cur) return;
      const prev = cur.modules.find((m) => m.id === moduleId);
      if (prev && prev.state !== "completed" && next.state === "completed") {
        setCelebrate(pickLocalized(next.title, lang, course.default_language) || t("modules.untitledModule"));
      }
      const updated = { ...cur, modules: cur.modules.map((m) => (m.id === moduleId ? next : m)) };
      dataRef.current = updated;
      setData(updated);
      // a completed module may open later ones (prerequisites): refresh quietly
      if (prev && prev.state !== next.state) void load(true);
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
  // exam-prep courses: the course layout shows no course header here, the page names itself
  if (early || !data) return <div className="flex w-full flex-col gap-4">{examPrep && <SyllabusTitle />}{early}</div>;
  return (
    <div className="flex w-full flex-col gap-4">
      {examPrep && <SyllabusTitle />}
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
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px] lg:items-start lg:gap-6">
        <div className="min-w-0 lg:col-start-1"><StartCard lessons={lessons} data={data} base={base} /></div>
        <aside className="min-w-0 lg:sticky lg:top-8 lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <AboutCard modules={data.modules.length} lessons={lessons.length} />
        </aside>
        <div className="min-w-0 space-y-4 lg:col-start-1">
          {rowError ? <ErrorState variant="inline" message={errorText(rowError)} /> : null}
          {data.modules.map((m) => (
            <ModuleSection key={m.id} mod={m} lessons={byModule.get(m.id) ?? []} ctx={ctx} open={!closed.has(m.id)}
              onToggle={() => setClosed((s) => {
                const n = new Set(s);
                if (n.has(m.id)) n.delete(m.id); else n.add(m.id);
                return n;
              })} />
          ))}
        </div>
      </div>
      {!readOnly && !examPrep && <LeaveCourseLink />}
    </div>
  );
}
