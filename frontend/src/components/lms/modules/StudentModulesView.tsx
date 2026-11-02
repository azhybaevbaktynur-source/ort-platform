"use client";

// Phase 8a S4a (PHASE_8A_DESIGN 8.1), UX rework B: a student's modules as Canvas-style groups: a module header (title,
// state, done / total; lock reasons in plain words) over compact rows in order (kind icon, title, kind + due date in
// small text, check mark when met, locked rows greyed with a lock icon and the reason). Tapping a page, file, assignment
// or link records the view, then opens it; "mark as done" items have a checkbox. A short line celebrates a completed
// module. The same list renders read-only for an org admin (no state) and in the teacher's progress drawer. From `xl`
// a right column lists this course's to-do.
import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Lock, PartyPopper } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { getModules, recordView, setDone } from "@/lib/lms/modules";
import { downloadCourseFile } from "@/lib/lms/courseFiles";
import { getHome } from "@/lib/lms/home";
import type { HomeTodoOut } from "@/lib/lms/homeTypes";
import type { ItemStudentOut, ModuleStudentOut, ModulesStudentOut } from "@/lib/lms/modulesTypes";
import type { Lang } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { fmtDayMonthTime } from "@/components/lms/home/format";
import { LeaveCourseLink } from "@/components/lms/home/LeaveCourseLink";
import { SideSection, TodoRows } from "@/components/lms/home/TodoList";
import { Checkbox, EmptyState, ErrorState, LoadingState, cn, focusRing } from "@/components/ui";
import { ExternalIcon, ItemKindIcon, ModuleStateBadge, itemHref, useItemKindText, useLockReasonText, useModuleErrorText, useRequirementText } from "./moduleUi";

type Mode = "student" | "readonly" | "progress";

interface ListCtx {
  base: string;
  courseId: string;
  defaultLang: Lang;
  mode: Mode;
  onFact: (moduleId: string, next: ModuleStudentOut) => void;
  onError: (e: unknown) => void;
}

function ItemRow({ item, module, ctx }: { item: ItemStudentOut; module: ModuleStudentOut; ctx: ListCtx }) {
  const { lang, t } = useTranslation();
  const kindText = useItemKindText();
  const reqText = useRequirementText();
  const [busy, setBusy] = useState(false);
  const title = pickLocalized(item.title, lang, ctx.defaultLang) || t("modules.untitledItem");
  const indent = Math.min(item.indent, 3);
  // indent only from sm up (375 px keeps the full width); static class names for Tailwind
  const pad = ["", "sm:pl-8", "sm:pl-12", "sm:pl-16"][indent];

  if (item.kind === "header") {
    return (
      <li className={cn("px-3 pb-1 pt-4 sm:px-4", pad)}>
        <h3 className="break-words text-sm font-semibold uppercase tracking-wide text-slate-600">{title}</h3>
      </li>
    );
  }

  const moduleLocked = module.state === "locked";
  // 8a UX M6: the server never marks a gating-exempt exam (ORT preset) as locked, even inside a locked module; such a
  // row opens and says where it lives. Every other item of a locked module is locked (the server says so too).
  const exempt = moduleLocked && !item.locked && item.kind === "assignment" && !!item.link?.assignment_id;
  const locked = item.locked || (moduleLocked && !exempt);
  const student = ctx.mode === "student";
  const req = item.requirement;
  const met = !!req?.met;
  const assignmentKind = item.link?.assignment_kind ?? null;

  const record = async () => {
    if (!student || locked) return;
    try {
      ctx.onFact(module.id, await recordView(ctx.courseId, module.id, item.id));
    } catch {
      // the view is a convenience fact; opening the target must not wait for it or fail because of it
    }
  };
  const toggleDone = async (done: boolean) => {
    setBusy(true);
    try {
      ctx.onFact(module.id, await setDone(ctx.courseId, module.id, item.id, done));
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

  const canOpen = !locked && ctx.mode !== "progress";
  // 8a UX M5: a file row names its action in the meta line at every width (like a page row's "View")
  const canDownload = canOpen && item.kind === "file" && !!item.link?.file_id;
  const meta = (
    <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm leading-5 text-slate-600 sm:text-xs">
      <span>{kindText(item.kind, assignmentKind)}</span>
      {item.due_at && <span>{t("home.todo.due", { date: fmtDayMonthTime(item.due_at, lang) })}</span>}
      {req && req.type !== "mark_done" && <span className={cn(met && "text-success-800")}>{reqText(req.type, req.threshold)}</span>}
      {req && req.best_score_percent !== null && req.best_score_percent !== undefined && !met && (
        <span>{t("modules.req.best", { percent: Math.round(req.best_score_percent) })}</span>
      )}
      {locked && !moduleLocked && <span className="text-slate-700">{t("modules.reason.sequentialItem")}</span>}
      {exempt && <span>{t("modules.availableInAssignments")}</span>}
      {canDownload && <span className="font-semibold text-brand-700">{t("modules.download")}</span>}
    </span>
  );

  const titleEl = <span className="block break-words text-base font-medium leading-6 sm:text-sm sm:leading-5">{title}</span>;
  const rowCls = cn("flex min-h-11 w-full items-center gap-3 px-3 py-2 text-left sm:px-4", pad);
  const linkFocus = cn(focusRing, "focus-visible:ring-inset focus-visible:ring-offset-0");
  const leading = <ItemKindIcon kind={item.kind} assignmentKind={assignmentKind} className={cn("h-5 w-5", locked ? "text-slate-400" : "text-slate-500")} />;
  // the state at the end of the row: a lock, or the check mark when the requirement is met
  const trailing = locked
    ? <Lock aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-400" />
    : met
      ? <span className="inline-flex shrink-0"><CheckCircle2 aria-hidden="true" className="h-5 w-5 text-success-700" /><span className="sr-only">{t("modules.req.met")}</span></span>
      : null;

  const href = itemHref(ctx.base, item.kind, item.link);
  let body: React.ReactNode;
  if (canOpen && href) {
    body = (
      <Link href={href} onClick={() => void record()} className={cn(rowCls, "text-slate-900 hover:bg-slate-50", linkFocus)}>
        {leading}<span className="min-w-0 flex-1">{titleEl}{meta}</span>{trailing}
      </Link>
    );
  } else if (canOpen && item.kind === "url" && item.link?.url) {
    body = (
      <a href={item.link.url} target="_blank" rel="noopener noreferrer" onClick={() => void record()}
        className={cn(rowCls, "text-slate-900 hover:bg-slate-50", linkFocus)}>
        {leading}
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">{titleEl}<ExternalIcon /><span className="sr-only">{t("modules.opensNewTab")}</span></span>
          {meta}
        </span>
        {trailing}
      </a>
    );
  } else if (canOpen && item.kind === "file" && item.link?.file_id) {
    body = (
      <button type="button" onClick={() => void openFile()} disabled={busy} aria-busy={busy || undefined}
        className={cn(rowCls, "text-slate-900 hover:bg-slate-50 disabled:opacity-70", linkFocus)}>
        {leading}<span className="min-w-0 flex-1">{titleEl}{meta}</span>{trailing}
      </button>
    );
  } else {
    body = (
      <div className={cn(rowCls, locked ? "text-slate-500" : "text-slate-900")} aria-disabled={locked || undefined}>
        {leading}<span className="min-w-0 flex-1">{titleEl}{meta}</span>{trailing}
      </div>
    );
  }

  if (req?.type !== "mark_done") return <li>{body}</li>;
  // "mark as done": under the row on phones, at its end from `sm`
  return (
    <li className="sm:flex sm:items-center">
      <div className="min-w-0 sm:flex-1">{body}</div>
      <div className="shrink-0 pl-11 pr-3 sm:pl-0 sm:pr-4">
        {student && !locked ? (
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

function ModuleCard({ module, ctx }: { module: ModuleStudentOut; ctx: ListCtx }) {
  const { lang, t } = useTranslation();
  const reasonText = useLockReasonText();
  const title = pickLocalized(module.title, lang, ctx.defaultLang) || t("modules.untitledModule");
  const withReq = module.items.filter((i) => i.requirement);
  const done = withReq.filter((i) => i.requirement?.met).length;
  const headingId = `module-${module.id}`;
  const hints = [
    withReq.length > 1 && module.completion_mode === "any" ? t("modules.completionAny") : "",
    module.sequential ? t("modules.sequentialHint") : "",
  ].filter(Boolean).join(" ");
  return (
    <section aria-labelledby={headingId} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-slate-200 bg-slate-50 px-3 py-2.5 sm:px-4" title={hints || undefined}>
        <h2 id={headingId} className="min-w-0 flex-1 basis-40 break-words text-base font-semibold leading-6 text-slate-900">{title}</h2>
        <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1">
          {withReq.length > 0 && <span className="text-sm leading-6 text-slate-600">{t("modules.progressCount", { done, total: withReq.length })}</span>}
          {/* no requirements = nothing to finish: "Completed" would be untrue for a new student */}
          {module.state && (module.state === "locked" || withReq.length > 0) && <ModuleStateBadge state={module.state} />}
        </div>
      </header>
      {module.state === "locked" && module.lock_reasons.length > 0 && (
        <ul className="space-y-1 border-b border-slate-100 px-3 py-2 text-sm leading-6 text-slate-700 sm:px-4">
          {module.lock_reasons.map((r, i) => (
            <li key={i} className="flex items-start gap-2"><Lock aria-hidden="true" className="mt-1 h-4 w-4 shrink-0" /><span className="break-words">{reasonText(r, ctx.defaultLang)}</span></li>
          ))}
        </ul>
      )}
      {module.items.length === 0 ? (
        <p className="px-3 py-3 text-base leading-6 text-slate-600 sm:px-4 sm:text-sm">{t("modules.noItemsStudent")}</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {module.items.map((item) => <ItemRow key={item.id} item={item} module={module} ctx={ctx} />)}
        </ul>
      )}
    </section>
  );
}

/** The modules list from a loaded payload (student, org admin or the teacher's progress drawer). */
export function ModuleList({ data, mode, onChange }: {
  data: ModulesStudentOut;
  mode: Mode;
  onChange?: (next: ModulesStudentOut, completedTitle?: string, reload?: boolean) => void;
}) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const errorText = useModuleErrorText();
  const [error, setError] = useState<unknown>(null);
  const ctx: ListCtx = {
    base: `/${lang}/courses/${course.id}`,
    courseId: course.id,
    defaultLang: course.default_language,
    mode,
    onError: setError,
    onFact: (moduleId, next) => {
      setError(null);
      const prev = data.modules.find((m) => m.id === moduleId);
      const modules = data.modules.map((m) => (m.id === moduleId ? next : m));
      const completed = prev && prev.state !== "completed" && next.state === "completed";
      onChange?.({ ...data, modules }, completed ? pickLocalized(next.title, lang, course.default_language) || t("modules.untitledModule") : undefined,
        !!prev && prev.state !== next.state);
    },
  };
  return (
    <div className="space-y-4">
      {error ? <ErrorState variant="inline" message={errorText(error)} /> : null}
      {data.modules.map((m) => <ModuleCard key={m.id} module={m} ctx={ctx} />)}
    </div>
  );
}

/** This course's to-do rows (section C data), read only while the right column can show them (`xl`, 1280 px). */
function useCourseTodo(courseId: string, enabled: boolean): HomeTodoOut[] {
  const [rows, setRows] = useState<HomeTodoOut[]>([]);
  const [wide, setWide] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(min-width: 1280px)");
    const onChange = () => setWide(query.matches);
    onChange();
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  const fetched = useRef(false);
  useEffect(() => {
    if (!wide || !enabled || fetched.current) return;
    fetched.current = true;
    // a convenience next to the list: without it the modules simply take the full width
    getHome().then((home) => setRows((home.todo ?? []).filter((r) => r.course_id === courseId))).catch(() => undefined);
  }, [wide, enabled, courseId]);
  return rows;
}

/**
 * `/courses/[id]/modules` for students and org admins, and the course home when modules are published. `fallback`:
 * rendered instead of the empty state when no module is visible (the course home falls back to today's layout).
 */
export function StudentModulesView({ fallback }: { fallback?: React.ReactNode }) {
  const { t } = useTranslation();
  const { course } = useCourse();
  const errorText = useModuleErrorText();
  const [data, setData] = useState<ModulesStudentOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [celebrate, setCelebrate] = useState<string | null>(null);
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError(null);
    try {
      const out = (await getModules(course.id)) as ModulesStudentOut;
      if (mounted.current) setData({ modules: out.modules ?? [], up_next: null }); // UX rework: no "up next" block
    } catch (e) {
      if (mounted.current) setError(e);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [course.id]);
  useEffect(() => { void load(); }, [load]);

  // concluded courses refuse new facts (403): the list stays readable, links still open
  const readOnly = course.my_enrollment.role !== "student" || !!course.my_enrollment.read_only || course.status === "concluded";

  const todo = useCourseTodo(course.id, !readOnly);

  let content: React.ReactNode;
  if (error && !data) content = <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />;
  else if (!data) content = <LoadingState rows={3} />;
  else if (data.modules.length === 0) {
    if (fallback !== undefined) return <>{fallback}</>;
    content = <EmptyState mascot="reading" title={t("modules.emptyStudentTitle")} description={t("modules.emptyStudentBody")} />;
  } else {
    content = (
      <ModuleList data={data} mode={readOnly ? "readonly" : "student"} onChange={(next, completedTitle, reload) => {
        setData(next);
        if (completedTitle) setCelebrate(completedTitle);
        // a completed module may open later ones (prerequisites): refresh quietly
        if (reload) void load(true);
      }} />
    );
  }

  return (
    <div className="flex w-full flex-col gap-4">{/* gap: the empty live region below takes no space */}
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
      <div className={cn(todo.length > 0 && "xl:grid xl:grid-cols-[minmax(0,1fr)_300px] xl:items-start xl:gap-6")}>
        <div className="min-w-0">{content}</div>
        {todo.length > 0 && (
          <aside className="hidden min-w-0 xl:block">
            <SideSection id="course-todo" title={t("home.todo.title")}><TodoRows rows={todo} showCourse={false} /></SideSection>
          </aside>
        )}
      </div>
      {data && data.modules.length > 0 && !readOnly && <LeaveCourseLink />}
    </div>
  );
}
