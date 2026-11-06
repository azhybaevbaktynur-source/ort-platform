"use client";

// Student UI U7 (docs/phases/STUDENT_UI_DESIGN.md §3.5) + F5b (COURSE_LESSONS_DESIGN L3, 4, 7.2): the lesson page
// `/courses/{c}/modules/{m}/items/{i}`. A video gets the click-to-load player, a page its content inline
// (`GET /pages/{id}`), a link or a file a small card. The course outline sits beside it from 1024 px (sticky, only the
// current module open) and in a collapsible under it on phones; a sticky bar holds "Назад" and "Следующий урок" (a
// locked next shows its lock and is disabled). The view fact is recorded when the student reaches the content: video
// on the play tap, page on open, file on the download click, link on the open click (idempotent on the server).
// Data: the student's evaluated outline (`GET /courses/{c}/modules`). A locked row comes without address, video, page
// or file id, so this page renders the lock card only: the Pro card with "Открыть доступ" or the module reasons with
// "К программе". The facts routes refuse locked items (403 / 423) on the server.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, CheckCircle2, ChevronDown, ChevronLeft, Download, ExternalLink, Lock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { getModules, recordView, setDone } from "@/lib/lms/modules";
import { downloadCourseFile } from "@/lib/lms/courseFiles";
import { getPage } from "@/lib/lms/pages";
import type { PageAnyOut } from "@/lib/lms/pagesTypes";
import { templateUi } from "@/lib/lms/templates";
import { isStaffModules, type ModuleStudentOut, type ModulesStudentOut } from "@/lib/lms/modulesTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { useStudentShellDataContext } from "@/components/lms/student/StudentShellDataContext";
import { STUDENT_TITLE } from "@/components/lms/student/StudentPageHeader";
import { SafeHtml } from "@/components/lms/pages/SafeHtml";
import { Button, EmptyState, ErrorState, LinkButton, LoadingState, buttonClasses, cn, focusRing } from "@/components/ui";
import { useLockReasonText, useModuleErrorText, useRequirementText } from "./moduleUi";
import { formatDuration, isAccessLocked, isDone, isLocked, lessonHref, lessonList, type LessonRef } from "./lessons";
import { rememberLessonModules } from "./lessonNav";
import { VideoPlayer } from "./VideoPlayer";
import { KindMeta, StatusIcon, viewOnOpen } from "./StudentSyllabus";
import { ProChip, ProLockCard } from "./ProLockCard";

/** The student's outline (student shape only; staff are sent to the course page). */
function useOutline() {
  const { lang } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const [data, setData] = useState<ModulesStudentOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError(null);
    try {
      const out = await getModules(course.id);
      if (isStaffModules(out)) {
        router.replace(`/${lang}/courses/${course.id}`);
        return;
      }
      setData({ modules: out.modules ?? [], up_next: out.up_next ?? null, progress: out.progress });
      rememberLessonModules(course.id, out.modules ?? []);
    } catch (e) {
      if (!quiet) setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id, lang, router]);
  useEffect(() => { void load(); }, [load]);
  return { data, setData, error, loading, load };
}

/** The course outline: every module, only the current one open; rows link where the overview's rows do. */
function LessonOutline({ data, lessons, current, idPrefix, track }: {
  data: ModulesStudentOut; lessons: LessonRef[]; current: LessonRef; idPrefix: string; track: boolean;
}) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const base = `/${lang}/courses/${course.id}`;
  const [open, setOpen] = useState<Set<string>>(() => new Set([current.mod.id]));
  return (
    <nav aria-label={t("modules.overview.outlineTitle")}>
      <ul className="space-y-1">
        {data.modules.map((m, n) => {
          const rows = lessons.filter((l) => l.mod.id === m.id);
          const isOpen = open.has(m.id);
          const listId = `${idPrefix}-${m.id}`;
          const title = pickLocalized(m.title, lang, course.default_language) || t("modules.untitledModule");
          const done = m.done ?? rows.filter((l) => isDone(l.item)).length;
          const total = m.total ?? rows.length;
          return (
            <li key={m.id}>
              <button type="button" aria-expanded={isOpen} aria-controls={listId}
                onClick={() => setOpen((s) => { const x = new Set(s); if (x.has(m.id)) x.delete(m.id); else x.add(m.id); return x; })}
                className={cn("flex min-h-11 w-full items-center gap-2 rounded-control px-2 text-left text-sm font-semibold leading-5 text-slate-900 hover:bg-slate-50", focusRing, "focus-visible:ring-offset-0")}>
                <ChevronDown aria-hidden="true" className={cn("h-4 w-4 shrink-0 text-slate-500 transition-transform", !isOpen && "-rotate-90")} />
                <span aria-hidden="true" className="w-4 shrink-0 text-center tabular-nums text-slate-500">{n + 1}</span>
                <span className="min-w-0 flex-1 break-words">{title}</span>
                {m.access_locked ? <ProChip /> : m.state === "locked"
                  ? <><Lock aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-400" /><span className="sr-only">{t("modules.overview.moduleLocked")}</span></>
                  : total > 0 && <span className="shrink-0 text-xs font-medium tabular-nums text-slate-600">{t("modules.overview.moduleDone", { done, total })}</span>}
              </button>
              <ul id={listId} hidden={!isOpen} className="mb-1 ml-2 space-y-0.5 border-l border-slate-200 pl-2">
                {rows.map((l) => {
                  const here = l.item.id === current.item.id;
                  const locked = isLocked(l.mod, l.item);
                  const name = pickLocalized(l.item.title, lang, course.default_language) || t("modules.untitledItem");
                  const inner = (
                    <>
                      <StatusIcon locked={locked} done={isDone(l.item)} current={here} />
                      <span className="line-clamp-2 min-w-0 flex-1 break-words">{name}</span>
                      <KindMeta item={l.item} locked={locked} className="text-xs" />
                    </>
                  );
                  const cls = cn("flex min-h-11 w-full items-center gap-2 rounded-control px-2 py-1.5 text-left text-sm leading-5", focusRing, "focus-visible:ring-offset-0");
                  return (
                    <li key={l.item.id}>
                      {locked && !here
                        ? <div aria-disabled="true" className={cn(cls, "text-slate-500")}>{inner}</div>
                        : (
                          <Link href={lessonHref(base, l)} onClick={viewOnOpen(course.id, l, track)} aria-current={here ? "page" : undefined}
                            className={cn(cls, here ? "bg-brand-50 font-semibold text-brand-800" : "text-slate-800 hover:bg-slate-50")}>
                            {inner}
                          </Link>
                        )}
                    </li>
                  );
                })}
              </ul>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** "Назад" and "Следующий урок" (course order, headers skipped), sticky at the bottom of the lesson column (above the
 * phone tab bar). A locked next is shown with its lock (the gold chip for Pro) and disabled. */
export function LessonPager({ lessons, current, nextPrimary, aboveTabBar, track }: {
  lessons: LessonRef[]; current: LessonRef; nextPrimary: boolean; aboveTabBar: boolean; track: boolean;
}) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const base = `/${lang}/courses/${course.id}`;
  const prev = current.index > 0 ? lessons[current.index - 1] : null;
  const next = current.index < lessons.length - 1 ? lessons[current.index + 1] : null;
  if (!prev && !next) return null;
  const titleOf = (l: LessonRef) => pickLocalized(l.item.title, lang, course.default_language) || t("modules.untitledItem");
  const nextLocked = !!next && isLocked(next.mod, next.item);
  return (
    <nav aria-label={t("modules.lesson.pagerLabel")}
      className={cn("sticky z-20 flex items-center gap-3 rounded-card border border-slate-200 bg-white/95 p-3 shadow-sm backdrop-blur",
        aboveTabBar ? "bottom-[calc(4.5rem+env(safe-area-inset-bottom))] lg:bottom-4" : "bottom-2 lg:bottom-4")}>
      {prev ? (
        <Link href={lessonHref(base, prev)} onClick={viewOnOpen(course.id, prev, track)} title={titleOf(prev)}
          className={buttonClasses({ variant: "secondary", className: "min-w-0 shrink-0 sm:max-w-[45%]" })}>
          <ArrowLeft aria-hidden="true" className="h-4 w-4 shrink-0" />
          <span className="sm:hidden">{t("modules.lesson.prevShort")}</span>
          <span className="hidden min-w-0 truncate sm:inline">{titleOf(prev)}</span>
          <span className="sr-only">{`, ${t("modules.lesson.prev")}`}</span>
        </Link>
      ) : <span />}
      {next && (nextLocked ? (
        <span aria-disabled="true" className={buttonClasses({ variant: "secondary", className: "ml-auto min-w-0 cursor-not-allowed opacity-70" })}>
          <span className="truncate sm:hidden">{t("modules.lesson.nextShort")}</span><span className="hidden truncate sm:inline">{t("modules.lesson.next")}</span>
          {isAccessLocked(next.item) ? <ProChip /> : <Lock aria-hidden="true" className="h-4 w-4 shrink-0" />}
          <span className="sr-only">{`: ${titleOf(next)}, ${t("modules.syllabus.status.locked")}`}</span>
        </span>
      ) : (
        <Link href={lessonHref(base, next)} onClick={viewOnOpen(course.id, next, track)} title={titleOf(next)}
          className={buttonClasses({ variant: nextPrimary ? "primary" : "secondary", className: "ml-auto min-w-0" })}>
          <span className="truncate">{t("modules.lesson.next")}</span>
          <span className="sr-only">{`: ${titleOf(next)}`}</span>
          <ArrowRight aria-hidden="true" className="h-4 w-4 shrink-0" />
        </Link>
      ))}
    </nav>
  );
}

/** A page lesson: the page's sanitized HTML inline (KaTeX in SafeHtml); `onOpen` once it is shown. */
function PageLessonBody({ pageId, onOpen }: { pageId: string; onOpen: () => void }) {
  const { course } = useCourse();
  const errorText = useModuleErrorText();
  const [page, setPage] = useState<PageAnyOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const opened = useRef(onOpen);
  opened.current = onOpen;
  useEffect(() => {
    let live = true;
    setPage(null); setError(null);
    getPage(course.id, pageId)
      .then((p) => { if (!live) return; setPage(p); opened.current(); })
      .catch((e) => { if (live) setError(e); });
    return () => { live = false; };
  }, [course.id, pageId]);
  if (error) return <ErrorState variant="inline" message={errorText(error)} />;
  if (!page) return <LoadingState rows={3} />;
  return (
    <article className="min-w-0 rounded-card border border-slate-200 bg-white p-4 sm:p-6">
      <SafeHtml html={page.body_html} />
    </article>
  );
}

export function LessonView({ moduleId, itemId }: { moduleId: string; itemId: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const shell = useStudentShellDataContext();
  const reasonText = useLockReasonText();
  const reqText = useRequirementText();
  const errorText = useModuleErrorText();
  const { data, setData, error, loading, load } = useOutline();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const base = `/${lang}/courses/${course.id}`;
  const examPrep = templateUi(course).studentLayout === "exam_prep";
  const readOnly = course.my_enrollment.role !== "student" || !!course.my_enrollment.read_only || course.status === "concluded";

  const lessons = useMemo(() => lessonList(data?.modules ?? []), [data]);
  const current = lessons.find((l) => l.item.id === itemId && l.mod.id === moduleId) ?? null;
  const locked = current ? isLocked(current.mod, current.item) : false;
  const forward = !!current && !locked && current.item.kind === "assignment";

  const replaceModule = useCallback((next: ModuleStudentOut) => {
    setData((cur) => (cur ? { ...cur, modules: cur.modules.map((m) => (m.id === next.id ? next : m)) } : cur));
  }, [setData]);

  // assignments have their own route (the lobby)
  useEffect(() => {
    if (forward && current) router.replace(lessonHref(base, current));
  }, [forward, current, base, router]);

  // the view fact, once per lesson, when the student reaches the content (design 4); the course bar refreshes after
  const viewed = useRef(false);
  const curModule = current?.mod.id ?? null;
  const curItem = current?.item.id ?? null;
  const curDone = current ? isDone(current.item) : false;
  const markViewed = useCallback(() => {
    if (!curModule || !curItem || locked || readOnly || viewed.current) return;
    viewed.current = true;
    if (curDone) return;
    recordView(course.id, curModule, curItem)
      .then((m) => { replaceModule(m); void load(true); })
      .catch(() => undefined); // a convenience fact: the content is already open
  }, [curModule, curItem, curDone, locked, readOnly, course.id, replaceModule, load]);

  if (error && !data) return <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />;
  if (!data || forward) return <LoadingState rows={4} />;

  const back = (label: string) => (
    <Link href={`${base}/modules`} className={cn("inline-flex min-h-11 items-center gap-1 rounded-control text-sm font-medium text-brand-700 hover:underline", focusRing)}>
      <ChevronLeft aria-hidden="true" className="h-4 w-4 shrink-0" /><span className="min-w-0 break-words">{label}</span>
    </Link>
  );
  if (!current) {
    return (
      <div className="space-y-4">
        {back(t("modules.overview.syllabusTitle"))}
        <EmptyState mascot="thinking" title={t("modules.lesson.notFoundTitle")} description={t("modules.lesson.notFoundBody")}
          action={<LinkButton href={`${base}/modules`} variant="secondary">{t("modules.overview.toSyllabus")}</LinkButton>} />
      </div>
    );
  }

  const { mod, item } = current;
  const title = pickLocalized(item.title, lang, course.default_language) || t("modules.untitledItem");
  const moduleTitle = pickLocalized(mod.title, lang, course.default_language) || t("modules.untitledModule");
  const inModule = lessons.filter((l) => l.mod.id === mod.id);
  const position = inModule.findIndex((l) => l.item.id === item.id) + 1;
  const req = item.requirement;
  const met = !!req?.met;
  const done = isDone(item);
  const accessLocked = locked && isAccessLocked(item);
  const duration = formatDuration(item.duration_s, t);

  const toggleDone = async (value: boolean) => {
    setBusy(true);
    setActionError(null);
    try {
      replaceModule(await setDone(course.id, mod.id, item.id, value));
      void load(true);
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };
  const download = async () => {
    if (!item.link?.file_id) return;
    setBusy(true);
    setActionError(null);
    markViewed();
    try {
      await downloadCourseFile(course.id, item.link.file_id);
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };

  // the body's own action is the page's primary until the lesson is done; then "Следующий урок" is
  const bodyPrimary = !done && (item.kind === "file" || (item.kind === "url" && !item.video));
  let body: React.ReactNode;
  if (accessLocked) {
    body = <ProLockCard />;
  } else if (locked) {
    const reasons = mod.state === "locked" ? mod.lock_reasons.map((r) => reasonText(r, course.default_language)) : [t("modules.reason.sequentialItem")];
    body = (
      <div className="rounded-card border border-slate-200 bg-white p-5">
        <p className="flex items-center gap-2 text-base font-semibold text-slate-900"><Lock aria-hidden="true" className="h-5 w-5 text-slate-500" />{t("modules.lesson.lockedTitle")}</p>
        {reasons.length > 0 && (
          <ul className="mt-2 space-y-1 text-sm leading-6 text-slate-700">{reasons.map((r, i) => <li key={i} className="break-words">{r}</li>)}</ul>
        )}
        <LinkButton href={`${base}/modules`} variant="secondary" className="mt-4 w-full sm:w-auto">{t("modules.overview.toSyllabus")}</LinkButton>
      </div>
    );
  } else if (item.kind === "url" && item.video) {
    body = <VideoPlayer key={item.id} video={item.video} title={title} onPlay={markViewed} />;
  } else if (item.kind === "page" && item.link?.page_id) {
    body = <PageLessonBody key={item.link.page_id} pageId={item.link.page_id} onOpen={markViewed} />;
  } else if (item.kind === "url" && item.link?.url) {
    body = (
      <div className="rounded-card border border-slate-200 bg-white p-5">
        <p className="text-base font-semibold text-slate-900">{t("modules.lesson.externalTitle")}</p>
        <p className="mt-1 text-sm leading-5 text-slate-600">{t("modules.lesson.externalBody")}</p>
        <a href={item.link.url} target="_blank" rel="noopener noreferrer" onClick={markViewed}
          className={buttonClasses({ variant: bodyPrimary ? "primary" : "secondary", className: "mt-4 w-full sm:w-auto" })}>
          {t("modules.lesson.openLink")}<ExternalLink aria-hidden="true" className="h-4 w-4" /><span className="sr-only">{t("modules.opensNewTab")}</span>
        </a>
      </div>
    );
  } else if (item.kind === "file" && item.link?.file_id) {
    body = (
      <div className="rounded-card border border-slate-200 bg-white p-5">
        <p className="text-sm leading-5 text-slate-600">{t("modules.lesson.fileBody")}</p>
        <Button className="mt-3 w-full sm:w-auto" variant={bodyPrimary ? "primary" : "secondary"} onClick={() => void download()} loading={busy}
          leftIcon={<Download aria-hidden="true" className="h-4 w-4" />}>
          {t("modules.download")}
        </Button>
      </div>
    );
  }

  let doneRow: React.ReactNode = null;
  if (req && !locked) {
    if (met) {
      doneRow = (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <p className="inline-flex items-center gap-2 text-base font-semibold text-success-800"><CheckCircle2 aria-hidden="true" className="h-5 w-5" />{t("modules.lesson.done")}</p>
          {req.type === "mark_done" && !readOnly && (
            <Button variant="link" onClick={() => void toggleDone(false)} disabled={busy}>{t("modules.lesson.undo")}</Button>
          )}
        </div>
      );
    } else if (req.type === "mark_done" && !readOnly) {
      doneRow = (
        <Button variant="secondary" className="w-full sm:w-auto" onClick={() => void toggleDone(true)} loading={busy} leftIcon={<CheckCircle2 aria-hidden="true" className="h-4 w-4" />}>
          {t("modules.lesson.markDone")}
        </Button>
      );
    } else {
      doneRow = <p className="text-sm leading-5 text-slate-600">{reqText(req.type, req.threshold)}</p>;
    }
  } else if (!locked && done) {
    doneRow = <p className="inline-flex items-center gap-2 text-sm font-medium text-success-800"><CheckCircle2 aria-hidden="true" className="h-4 w-4" />{t("modules.lesson.done")}</p>;
  }

  const moduleDone = mod.done ?? inModule.filter((l) => isDone(l.item)).length;
  const moduleTotal = mod.total ?? inModule.length;
  return (
    <div className="grid w-full gap-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
      <div className="flex min-w-0 flex-col gap-5">
        <div className="min-w-0">
          <nav aria-label={t("modules.overview.breadcrumbLabel")} className="flex flex-wrap items-center gap-x-1.5 text-sm leading-5 text-slate-600">
            <span className="hidden sm:inline">{back(t("modules.overview.syllabusTitle"))}</span>
            <span className="sm:hidden">{back(moduleTitle)}</span>
            <span aria-hidden="true" className="hidden sm:inline">·</span>
            <span className="hidden break-words sm:inline">{moduleTitle}</span>
            <span aria-hidden="true">·</span>
            <span className="tabular-nums">{t("modules.lesson.positionShort", { n: position, total: inModule.length })}</span>
          </nav>
          {/* exam-prep courses show no course header here: the lesson title is the page's h1 */}
          {examPrep
            ? <h1 className={cn(STUDENT_TITLE, "mt-1")}>{title}</h1>
            : <h2 className="mt-1 break-words text-2xl font-bold leading-8 text-slate-900">{title}</h2>}
          {!locked && duration && <p className="mt-1 text-sm leading-5 text-slate-600"><KindMeta item={item} locked={false} /></p>}
        </div>
        {body}
        {actionError ? <ErrorState variant="inline" message={errorText(actionError)} /> : null}
        {doneRow && <div className="flex flex-col sm:items-start">{doneRow}</div>}
        <details className="group rounded-card border border-slate-200 bg-white lg:hidden">
          <summary className={cn("flex min-h-12 cursor-pointer list-none items-center gap-2 px-4 text-base font-semibold text-slate-900 [&::-webkit-details-marker]:hidden", focusRing, "focus-visible:ring-inset focus-visible:ring-offset-0")}>
            <ChevronDown aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-500 transition-transform group-[:not([open])]:-rotate-90" />
            <span className="min-w-0 flex-1">{t("modules.overview.outlineTitle")}</span>
            <span className="shrink-0 text-sm font-medium tabular-nums text-slate-600">{t("modules.overview.moduleDone", { done: moduleDone, total: moduleTotal })}</span>
          </summary>
          <div className="border-t border-slate-100 p-2">
            <LessonOutline data={data} lessons={lessons} current={current} idPrefix="outline-phone" track={!readOnly} />
          </div>
        </details>
        <LessonPager lessons={lessons} current={current} nextPrimary={!bodyPrimary && !accessLocked} aboveTabBar={!!shell} track={!readOnly} />
      </div>
      <aside className="hidden min-w-0 lg:sticky lg:top-8 lg:block lg:max-h-[calc(100vh-4rem)] lg:overflow-y-auto">
        <div className="rounded-card border border-slate-200 bg-white p-3">
          <h2 className="px-2 pb-2 pt-1 text-base font-semibold leading-6 text-slate-900">{t("modules.overview.outlineTitle")}</h2>
          <LessonOutline data={data} lessons={lessons} current={current} idPrefix="outline-desk" track={!readOnly} />
        </div>
      </aside>
    </div>
  );
}
