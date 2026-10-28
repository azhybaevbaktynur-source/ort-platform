"use client";

// Phase 8a S4a (PHASE_8A_DESIGN 8.1): a student's modules. "Up next" on top with the page's one primary action, then
// the modules as cards (state badge, lock reasons in plain words) and their items as rows (kind icon + text, check
// mark when met, requirement text, locked rows greyed with a lock icon and text). Tapping a page, file, assignment or
// link records the view, then opens it; "mark as done" items have a checkbox. A short line celebrates a completed
// module. The same list renders read-only for an org admin (no state) and in the teacher's progress drawer.
import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Lock, PartyPopper } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { getModules, recordView, setDone } from "@/lib/lms/modules";
import { downloadCourseFile } from "@/lib/lms/courseFiles";
import type { ItemRefOut, ItemStudentOut, ModuleStudentOut, ModulesStudentOut } from "@/lib/lms/modulesTypes";
import type { Lang } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { Button, Card, Checkbox, EmptyState, ErrorState, LinkButton, LoadingState, cn, focusRing } from "@/components/ui";
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
    <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm leading-6 text-slate-600">
      <span className="inline-flex items-center gap-1"><ItemKindIcon kind={item.kind} assignmentKind={assignmentKind} />{kindText(item.kind, assignmentKind)}</span>
      {req && req.type !== "mark_done" && (
        <span className={cn("inline-flex items-center gap-1", met && "text-success-800")}>
          {met && <CheckCircle2 aria-hidden="true" className="h-4 w-4" />}
          {reqText(req.type, req.threshold)}
          {met && <span className="sr-only">{t("modules.req.met")}</span>}
        </span>
      )}
      {req && req.best_score_percent !== null && req.best_score_percent !== undefined && !met && (
        <span>{t("modules.req.best", { percent: Math.round(req.best_score_percent) })}</span>
      )}
      {locked && !moduleLocked && (
        <span className="inline-flex items-center gap-1 text-slate-700"><Lock aria-hidden="true" className="h-4 w-4" />{t("modules.reason.sequentialItem")}</span>
      )}
      {exempt && <span>{t("modules.availableInAssignments")}</span>}
      {canDownload && <span className="font-semibold text-brand-700">{t("modules.download")}</span>}
    </span>
  );

  const titleEl = <span className="block break-words text-base font-semibold leading-6">{title}</span>;
  const rowCls = cn("flex min-h-11 w-full items-start gap-3 rounded-xl px-3 py-3 text-left sm:px-4", pad);
  const leading = locked
    ? <Lock aria-hidden="true" className="mt-1 h-5 w-5 shrink-0 text-slate-400" />
    : met
      ? <CheckCircle2 aria-hidden="true" className="mt-1 h-5 w-5 shrink-0 text-success-700" />
      : <ItemKindIcon kind={item.kind} assignmentKind={assignmentKind} className="mt-1 h-5 w-5 text-slate-500" />;

  const href = itemHref(ctx.base, item.kind, item.link);
  let body: React.ReactNode;
  if (canOpen && href) {
    body = (
      <Link href={href} onClick={() => void record()} className={cn(rowCls, "text-slate-900 hover:bg-slate-50", focusRing)}>
        {leading}<span className="min-w-0 flex-1">{titleEl}{meta}</span>
      </Link>
    );
  } else if (canOpen && item.kind === "url" && item.link?.url) {
    body = (
      <a href={item.link.url} target="_blank" rel="noopener noreferrer" onClick={() => void record()}
        className={cn(rowCls, "text-slate-900 hover:bg-slate-50", focusRing)}>
        {leading}
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">{titleEl}<ExternalIcon /><span className="sr-only">{t("modules.opensNewTab")}</span></span>
          {meta}
        </span>
      </a>
    );
  } else if (canOpen && item.kind === "file" && item.link?.file_id) {
    body = (
      <button type="button" onClick={() => void openFile()} disabled={busy} aria-busy={busy || undefined}
        className={cn(rowCls, "text-slate-900 hover:bg-slate-50 disabled:opacity-70", focusRing)}>
        {leading}<span className="min-w-0 flex-1">{titleEl}{meta}</span>
      </button>
    );
  } else {
    body = (
      <div className={cn(rowCls, locked ? "text-slate-500" : "text-slate-900")} aria-disabled={locked || undefined}>
        {leading}<span className="min-w-0 flex-1">{titleEl}{meta}</span>
      </div>
    );
  }

  return (
    <li>
      {body}
      {req?.type === "mark_done" && (
        <div className={cn("px-3 pb-3 sm:px-4", pad)}>
          <div className="pl-8">
            {student && !locked ? (
              <Checkbox label={t("modules.markDone")} checked={met} disabled={busy} onChange={(e) => void toggleDone(e.target.checked)} />
            ) : (
              <span className={cn("inline-flex items-center gap-1 text-sm", met ? "text-success-800" : "text-slate-600")}>
                {met && <CheckCircle2 aria-hidden="true" className="h-4 w-4" />}
                {met ? t("modules.req.markedDone") : t("modules.req.mark_done")}
              </span>
            )}
          </div>
        </div>
      )}
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
  return (
    <section aria-labelledby={headingId} className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <header className="flex flex-col gap-2 border-b border-slate-100 px-4 py-4 sm:flex-row sm:items-start sm:justify-between sm:px-6">
        <div className="min-w-0">
          <h2 id={headingId} className="break-words text-lg font-semibold leading-7 text-slate-900">{title}</h2>
          <p className="mt-0.5 flex flex-wrap gap-x-3 text-sm leading-6 text-slate-600">
            {withReq.length > 0 && <span>{t("modules.progressCount", { done, total: withReq.length })}</span>}
            {withReq.length > 1 && module.completion_mode === "any" && <span>{t("modules.completionAny")}</span>}
            {module.sequential && <span>{t("modules.sequentialHint")}</span>}
          </p>
        </div>
        {module.state && <div className="shrink-0"><ModuleStateBadge state={module.state} /></div>}
      </header>
      {module.state === "locked" && module.lock_reasons.length > 0 && (
        <ul className="space-y-1 border-b border-slate-100 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700 sm:px-6">
          {module.lock_reasons.map((r, i) => (
            <li key={i} className="flex items-start gap-2"><Lock aria-hidden="true" className="mt-1 h-4 w-4 shrink-0" /><span className="break-words">{reasonText(r, ctx.defaultLang)}</span></li>
          ))}
        </ul>
      )}
      {module.items.length === 0 ? (
        <p className="px-4 py-4 text-base text-slate-600 sm:px-6">{t("modules.noItemsStudent")}</p>
      ) : (
        <ul className="divide-y divide-slate-100 p-1 sm:p-2">
          {module.items.map((item) => <ItemRow key={item.id} item={item} module={module} ctx={ctx} />)}
        </ul>
      )}
    </section>
  );
}

function UpNext({ up, ctx, allDone }: { up: ItemRefOut | null; ctx: ListCtx; allDone: boolean }) {
  const { lang, t } = useTranslation();
  const kindText = useItemKindText();
  const errorText = useModuleErrorText();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (!up) {
    if (!allDone) return null;
    return (
      <p role="status" className="flex items-start gap-2 rounded-xl border border-success-200 bg-success-50 px-4 py-3 text-base leading-6 text-success-900">
        <CheckCircle2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />{t("modules.upNext.allDone")}
      </p>
    );
  }
  const title = pickLocalized(up.title, lang, ctx.defaultLang) || t("modules.untitledItem");
  const moduleTitle = pickLocalized(up.module_title, lang, ctx.defaultLang) || t("modules.untitledModule");
  const record = () => { if (ctx.mode === "student") void recordView(ctx.courseId, up.module_id, up.item_id).then((m) => ctx.onFact(up.module_id, m)).catch(() => undefined); };
  const href = itemHref(ctx.base, up.kind, up.link);
  const label = t("modules.upNext.action");
  let action: React.ReactNode = null;
  if (href) action = <LinkButton size="lg" href={href} onClick={record}>{label}</LinkButton>;
  else if (up.kind === "url" && up.link?.url) {
    action = (
      <a href={up.link.url} target="_blank" rel="noopener noreferrer" onClick={record}
        className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-brand-600 px-5 text-base font-semibold text-white shadow-sm hover:bg-brand-700">
        {label}<ExternalIcon /><span className="sr-only">{t("modules.opensNewTab")}</span>
      </a>
    );
  } else if (up.kind === "file" && up.link?.file_id) {
    const fileId = up.link.file_id;
    action = (
      <Button size="lg" loading={busy} onClick={async () => {
        setBusy(true); setError(null); record();
        try { await downloadCourseFile(ctx.courseId, fileId); } catch (e) { setError(e); } finally { setBusy(false); }
      }}>{t("modules.download")}</Button>
    );
  }
  return (
    <Card title={t("modules.upNext.title")} headingLevel={2}>
      <p className="text-sm leading-6 text-slate-600">{moduleTitle}</p>
      <p className="mt-0.5 flex items-start gap-2 break-words text-lg font-semibold leading-7 text-slate-900">
        <ItemKindIcon kind={up.kind} assignmentKind={up.link?.assignment_kind} className="mt-1.5 h-5 w-5 text-slate-500" />
        <span className="min-w-0">{title}<span className="sr-only">, {kindText(up.kind, up.link?.assignment_kind)}</span></span>
      </p>
      {action && <div className="mt-4 [&>*]:w-full sm:[&>*]:w-auto">{action}</div>}
      {error ? <p role="alert" className="mt-2 text-sm text-danger-700">{errorText(error)}</p> : null}
    </Card>
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
  const allDone = data.modules.length > 0 && data.modules.every((m) => m.state === "completed");
  return (
    <div className="space-y-6">
      {mode === "student" && <UpNext up={data.up_next} ctx={ctx} allDone={allDone} />}
      {error ? <ErrorState variant="inline" message={errorText(error)} /> : null}
      {data.modules.map((m) => <ModuleCard key={m.id} module={m} ctx={ctx} />)}
    </div>
  );
}

/**
 * `/courses/[id]/modules` for students and org admins, and the course home when `home_kind = modules`. `fallback`:
 * rendered instead of the empty state when no module is published (the course home falls back to today's layout).
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
      if (mounted.current) setData({ modules: out.modules ?? [], up_next: out.up_next ?? null });
    } catch (e) {
      if (mounted.current) setError(e);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [course.id]);
  useEffect(() => { void load(); }, [load]);

  // concluded courses refuse new facts (403): the list stays readable, links still open
  const readOnly = course.my_enrollment.role !== "student" || !!course.my_enrollment.read_only || course.status === "concluded";

  let content: React.ReactNode;
  if (error && !data) content = <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />;
  else if (!data) content = <LoadingState rows={3} />;
  else if (data.modules.length === 0) {
    if (fallback) return <>{fallback}</>;
    content = <EmptyState title={t("modules.emptyStudentTitle")} description={t("modules.emptyStudentBody")} />;
  } else {
    content = (
      <ModuleList data={data} mode={readOnly ? "readonly" : "student"} onChange={(next, completedTitle, reload) => {
        setData(next);
        if (completedTitle) setCelebrate(completedTitle);
        // a completed module may open later ones (prerequisites) and moves "up next": refresh quietly
        if (reload) void load(true);
      }} />
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      {course.status === "concluded" && (
        <p role="status" className="rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-base leading-6 text-slate-700 sm:text-sm">{t("courses.home.concludedNotice")}</p>
      )}
      <div aria-live="polite">
        {celebrate && (
          <p className="flex items-start gap-2 rounded-xl border border-success-200 bg-success-50 px-4 py-3 text-base leading-6 text-success-900">
            <PartyPopper aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />{t("modules.celebrate", { title: celebrate })}
          </p>
        )}
      </div>
      {content}
    </div>
  );
}
