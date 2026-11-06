"use client";

// Student UI U7 (docs/phases/STUDENT_UI_DESIGN.md §3.5): the lesson page `/courses/{c}/modules/{m}/items/{i}`. A video
// item gets the click-to-load player; a plain link or a file gets a small card (open in a new tab / download). The
// item's module and position, "Mark as done" (a `mark_done` requirement) or the automatic view record, and the
// previous / next lesson. Pages and assignments keep their own routes (this page forwards there). The data is the
// student's evaluated outline (`GET /courses/{c}/modules`): a locked item comes without a destination or video, so this
// page can only say why it is locked; the facts routes refuse locked items (423) on the server.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, CheckCircle2, Download, ExternalLink, Lock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { getModules, recordView, setDone } from "@/lib/lms/modules";
import { downloadCourseFile } from "@/lib/lms/courseFiles";
import { templateUi } from "@/lib/lms/templates";
import { isStaffModules, type ModuleStudentOut, type ModulesStudentOut } from "@/lib/lms/modulesTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { Button, EmptyState, ErrorState, LinkButton, LoadingState, buttonClasses, cn, focusRing } from "@/components/ui";
import { useLockReasonText, useModuleErrorText, useRequirementText } from "./moduleUi";
import { isLocked, lessonHref, lessonList, type LessonRef } from "./lessons";
import { rememberLessonModules } from "./lessonNav";
import { VideoPlayer } from "./VideoPlayer";

/** The student's outline (student shape only; staff are sent to the course page). */
function useOutline() {
  const { lang } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const [data, setData] = useState<ModulesStudentOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const out = await getModules(course.id);
      if (isStaffModules(out)) {
        router.replace(`/${lang}/courses/${course.id}`);
        return;
      }
      setData({ modules: out.modules ?? [], up_next: out.up_next ?? null });
      rememberLessonModules(course.id, out.modules ?? []);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id, lang, router]);
  useEffect(() => { void load(); }, [load]);
  return { data, setData, error, loading, load };
}

/** Previous / next lesson (course order, headers skipped); a locked neighbour shows its lock. */
export function LessonPager({ lessons, current, className }: { lessons: LessonRef[]; current: LessonRef; className?: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const base = `/${lang}/courses/${course.id}`;
  const prev = current.index > 0 ? lessons[current.index - 1] : null;
  const next = current.index < lessons.length - 1 ? lessons[current.index + 1] : null;
  if (!prev && !next) return null;
  const card = (l: LessonRef, dir: "prev" | "next") => {
    const title = pickLocalized(l.item.title, lang, course.default_language) || t("modules.untitledItem");
    const locked = isLocked(l.mod, l.item);
    return (
      <Link href={lessonHref(base, l)}
        className={cn("flex min-h-16 items-center gap-3 rounded-card border border-slate-200 bg-white px-4 py-3 hover:bg-slate-50", focusRing,
          dir === "next" && "sm:col-start-2 sm:flex-row-reverse sm:text-right")}>
        {dir === "prev"
          ? <ArrowLeft aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-500" />
          : <ArrowRight aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-500" />}
        <span className="min-w-0 flex-1">
          <span className="block text-xs font-medium uppercase tracking-wide text-slate-600">{t(dir === "prev" ? "modules.lesson.prev" : "modules.lesson.next")}</span>
          <span className={cn("mt-0.5 flex items-center gap-1.5 break-words text-sm font-semibold leading-5 text-slate-900", dir === "next" && "sm:justify-end")}>
            {locked && <Lock aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-400" />}
            <span className="min-w-0 break-words">{title}</span>
            {locked && <span className="sr-only">{t("modules.syllabus.status.locked")}</span>}
          </span>
        </span>
      </Link>
    );
  };
  return (
    <nav aria-label={t("modules.lesson.pagerLabel")} className={cn("grid gap-3 sm:grid-cols-2", className)}>
      {prev && card(prev, "prev")}
      {next && card(next, "next")}
    </nav>
  );
}

/** The prev / next footer under a page opened from the syllabus (`?m=&i=`); nothing when the lesson is unknown. */
export function PageLessonFooter({ moduleId, itemId }: { moduleId: string; itemId: string }) {
  const { data } = useOutline();
  const lessons = useMemo(() => lessonList(data?.modules ?? []), [data]);
  const current = lessons.find((l) => l.item.id === itemId && l.mod.id === moduleId);
  if (!current) return null;
  return <LessonPager lessons={lessons} current={current} className="mt-8" />;
}

export function LessonView({ moduleId, itemId }: { moduleId: string; itemId: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
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
  const forward = !!current && !locked && (current.item.kind === "page" || current.item.kind === "assignment");

  const replaceModule = useCallback((next: ModuleStudentOut) => {
    setData((cur) => (cur ? { ...cur, modules: cur.modules.map((m) => (m.id === next.id ? next : m)) } : cur));
  }, [setData]);

  // pages and assignments have their own routes
  useEffect(() => {
    if (forward && current) router.replace(lessonHref(base, current));
  }, [forward, current, base, router]);

  // opening the lesson is the "view" fact (idempotent on the server)
  const viewed = useRef(false);
  useEffect(() => {
    if (!current || locked || forward || readOnly || viewed.current) return;
    viewed.current = true;
    recordView(course.id, current.mod.id, current.item.id).then(replaceModule).catch(() => undefined);
  }, [current, locked, forward, readOnly, course.id, replaceModule]);

  if (error && !data) return <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />;
  if (!data || forward) return <LoadingState rows={4} />;

  const back = (
    <Link href={`${base}/modules`} className={cn("inline-flex min-h-11 items-center gap-1.5 rounded-control text-sm font-medium text-brand-700 hover:underline", focusRing)}>
      <ArrowLeft aria-hidden="true" className="h-4 w-4" />{t("modules.lesson.back")}
    </Link>
  );
  if (!current) {
    return (
      <div className="space-y-4">
        {back}
        <EmptyState mascot="thinking" title={t("modules.lesson.notFoundTitle")} description={t("modules.lesson.notFoundBody")}
          action={<LinkButton href={`${base}/modules`} variant="secondary">{t("modules.lesson.back")}</LinkButton>} />
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

  const toggleDone = async (done: boolean) => {
    setBusy(true);
    setActionError(null);
    try {
      replaceModule(await setDone(course.id, mod.id, item.id, done));
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
    try {
      await downloadCourseFile(course.id, item.link.file_id);
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };

  let body: React.ReactNode;
  if (locked) {
    const reasons = mod.state === "locked" ? mod.lock_reasons.map((r) => reasonText(r, course.default_language)) : [t("modules.reason.sequentialItem")];
    body = (
      <div className="rounded-card border border-slate-200 bg-white p-5">
        <p className="flex items-center gap-2 text-base font-semibold text-slate-900"><Lock aria-hidden="true" className="h-5 w-5 text-slate-500" />{t("modules.lesson.lockedTitle")}</p>
        {reasons.length > 0 && (
          <ul className="mt-2 space-y-1 text-sm leading-6 text-slate-700">{reasons.map((r, i) => <li key={i} className="break-words">{r}</li>)}</ul>
        )}
      </div>
    );
  } else if (item.kind === "url" && item.video) {
    body = <VideoPlayer key={item.id} video={item.video} title={title} />;
  } else if (item.kind === "url" && item.link?.url) {
    body = (
      <div className="rounded-card border border-slate-200 bg-white p-5">
        <p className="text-base font-semibold text-slate-900">{t("modules.lesson.externalTitle")}</p>
        <p className="mt-1 text-sm leading-5 text-slate-600">{t("modules.lesson.externalBody")}</p>
        <a href={item.link.url} target="_blank" rel="noopener noreferrer" className={buttonClasses({ className: "mt-4 w-full sm:w-auto" })}>
          {t("modules.lesson.openLink")}<ExternalLink aria-hidden="true" className="h-4 w-4" /><span className="sr-only">{t("modules.opensNewTab")}</span>
        </a>
      </div>
    );
  } else if (item.kind === "file" && item.link?.file_id) {
    body = (
      <div className="rounded-card border border-slate-200 bg-white p-5">
        <p className="text-sm leading-5 text-slate-600">{t("modules.lesson.fileBody")}</p>
        <Button className="mt-3 w-full sm:w-auto" onClick={() => void download()} loading={busy} leftIcon={<Download aria-hidden="true" className="h-4 w-4" />}>
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
  }

  return (
    <div className="flex w-full max-w-[960px] flex-col gap-5">
      <div>{back}</div>
      <div className="min-w-0">
        <p className="break-words text-sm leading-5 text-slate-600">
          {moduleTitle} · {t("modules.lesson.position", { n: position, total: inModule.length })}
        </p>
        {/* exam-prep courses show no course header here: the lesson title is the page's h1 */}
        {examPrep
          ? <h1 className="mt-1 break-words text-2xl font-bold leading-8 text-slate-900 lg:text-[28px] lg:leading-9">{title}</h1>
          : <h2 className="mt-1 break-words text-2xl font-bold leading-8 text-slate-900">{title}</h2>}
      </div>
      {body}
      {actionError ? <ErrorState variant="inline" message={errorText(actionError)} /> : null}
      {doneRow && <div className="flex flex-col sm:items-start">{doneRow}</div>}
      <LessonPager lessons={lessons} current={current} className="border-t border-slate-200 pt-5" />
    </div>
  );
}
