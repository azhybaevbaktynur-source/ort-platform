"use client";

// Phase 8b S4: Sample questions tab (PHASE_8B_DESIGN 7, 9.1). `SandboxGate` creates (or syncs) the template's hidden
// sandbox course + sample quiz with `POST /exam-templates/{id}/sandbox`, then mounts the 7c card editor on it
// (`QuizEditor mode="sandbox"` under a CourseContext built from `GET /courses/{sandbox}`). `PreviewLauncher` starts
// a staff preview attempt and opens the real general player with `?return=` back here (new tab at lg:, same tab
// below). The server syncs the sample from the *stored* draft, so unsaved constructor changes are flushed first.
// Phase 8b UX: the launch state lives in `usePreviewLaunch` (owned by the editor) so the header "Preview" button
// starts the same preview; "preview not ready" is one amber callout naming the sections.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Eye, FlaskConical, Info, TriangleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { ensureTemplateSandbox, startTemplatePreview } from "@/lib/lms/examTemplates";
import type { ExamTemplateOut, SandboxOut } from "@/lib/lms/examTemplateTypes";
import { getCourse } from "@/lib/lms/courses";
import { getAssessment } from "@/lib/lms/assessments";
import { ISSUE_CODES, isStaffAssessment, type AssessmentStaffOut, type Issue } from "@/lib/lms/assessmentTypes";
import { LMS_LANGS, type CourseOut, type Lang } from "@/lib/lms/types";
import { CourseContext } from "@/components/lms/CourseContext";
import { QuizEditor } from "@/components/lms/quiz/QuizEditor";
import { IssueList, issuesFromDetails } from "@/components/lms/assessments/IssueList";
import { Button, Card, EmptyState, LoadingState, Select } from "@/components/ui";
import { ExamTemplateError } from "./ui";
import { splitOptions, type SpecDraft } from "./specDraft";
import type { SaveState } from "./useConstructor";

/** Preview opens in a new tab from this width up (Tailwind `lg`), in the same tab below. */
const NEW_TAB_QUERY = "(min-width: 1024px)";

/** Template parameters with options, as the preview offers them (from the constructor draft). */
export function previewParameters(draft: SpecDraft | null | undefined) {
  return (draft?.parameters ?? [])
    .map((p) => ({ key: p.key.trim(), options: splitOptions(p.options) }))
    .filter((p) => p.key && p.options.length);
}

export interface PreviewLaunch {
  busy: boolean;
  error: unknown;
  issues: Issue[];
  /** Chosen preview language (null: the UI language when the sample quiz has it, else its first language). */
  language: Lang | null;
  setLanguage: (l: Lang) => void;
  params: Record<string, string>;
  setParams: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  /** Starts a preview attempt and opens the player; false when it could not start (the error is kept here). */
  launch: (language?: Lang) => Promise<boolean>;
}

/**
 * The one "preview as student" action, shared by the constructor header and the Sample tab's launcher. Must be
 * called inside the click (a new tab is opened synchronously at lg: so popup blockers allow it).
 */
export function usePreviewLaunch(templateId: string, draft: SpecDraft | null | undefined, flush: () => Promise<boolean>): PreviewLaunch {
  const { lang } = useTranslation();
  const router = useRouter();
  const pathname = usePathname();
  const [language, setLanguage] = useState<Lang | null>(null);
  const [params, setParams] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [issues, setIssues] = useState<Issue[]>([]);

  const launch = useCallback(async (chosenLang?: Lang) => {
    // a new tab must be opened inside the click (popup blockers); it is pointed at the player once the attempt exists
    const wide = typeof window !== "undefined" && window.matchMedia(NEW_TAB_QUERY).matches;
    const win = wide ? window.open("", "_blank") : null;
    setBusy(true);
    setError(null);
    setIssues([]);
    try {
      await flush();
      const parameters = previewParameters(draft);
      const chosen = Object.fromEntries(parameters.map((p) => [p.key, params[p.key] || p.options[0]]));
      const body = parameters.length ? { parameters: chosen } : {};
      let out;
      const pick = chosenLang ?? language;
      try {
        out = await startTemplatePreview(templateId, { language: pick ?? lang, ...body });
      } catch (e) {
        // header button, nothing chosen and the sample quiz lacks the UI language: its own first language
        if (pick || (e as { code?: string }).code !== "language_not_in_assessment") throw e;
        out = await startTemplatePreview(templateId, body);
      }
      setIssues((out.issues ?? []) as unknown as Issue[]);
      const back = `${pathname}?tab=sample`;
      const url = `/${lang}/courses/${out.course_id}/attempts/${out.attempt_id}?return=${encodeURIComponent(back)}`;
      if (win) { win.opener = null; win.location.href = url; } else router.push(url);
      return true;
    } catch (e) {
      win?.close();
      setError(e);
      setIssues(issuesFromDetails((e as { details?: unknown }).details));
      return false;
    } finally {
      setBusy(false);
    }
  }, [templateId, draft, flush, params, language, lang, pathname, router]);

  return { busy, error, issues, language, setLanguage, params, setParams, launch };
}

export function SampleTab({ tpl, draft, active, archived, saveState, flush, preview, sectionName, onSandbox }: {
  tpl: ExamTemplateOut;
  draft: SpecDraft;
  /** The tab is visible: (re)sync when the stored draft changed since the last sync. */
  active: boolean;
  archived: boolean;
  saveState: SaveState;
  flush: () => Promise<boolean>;
  preview: PreviewLaunch;
  /** Section name by index (the constructor's resolver, as in the issues bar). */
  sectionName: (i: number) => string;
  /** The sandbox exists now (the header "Preview" may launch directly). */
  onSandbox?: () => void;
}) {
  const { lang, t } = useTranslation();
  const [sandbox, setSandbox] = useState<SandboxOut | null>(null);
  const [course, setCourse] = useState<CourseOut | null>(null);
  const [assessment, setAssessment] = useState<AssessmentStaffOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [firstLang, setFirstLang] = useState<Lang>(lang);
  const [editorKey, setEditorKey] = useState(0);
  const syncedRev = useRef<number | null>(null);
  const hasSandbox = !!tpl.sandbox || !!sandbox;

  const sync = useCallback(async (language?: Lang) => {
    setBusy(true);
    setError(null);
    try {
      await flush();
      const out = await ensureTemplateSandbox(tpl.id, language ? { language } : {});
      const [c, a] = await Promise.all([getCourse(out.course_id), getAssessment(out.course_id, out.assessment_id)]);
      if (!isStaffAssessment(a)) throw { code: "forbidden" };
      syncedRev.current = out.draft_rev;
      setSandbox(out);
      onSandbox?.();
      setCourse(c);
      setAssessment(a);
      setEditorKey((k) => k + 1);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }, [tpl.id, flush, onSandbox]);

  const rev = tpl.draft_rev ?? 0;
  useEffect(() => {
    if (!active || archived || busy || !hasSandbox || error) return;
    if (syncedRev.current === rev) return;
    void sync();
    // `busy`/`error` gate re-entry; `sync` identity changes with the template payload
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, archived, hasSandbox, rev]);

  const setCourseCtx = useCallback((c: CourseOut) => setCourse(c), []);
  const reloadCourse = useCallback(async () => {
    if (sandbox) setCourse(await getCourse(sandbox.course_id));
  }, [sandbox]);

  if (archived) {
    return (
      <EmptyState icon={<FlaskConical />} title={t("examTemplates.sandbox.archivedTitle")} description={t("examTemplates.errors.template_archived")} />
    );
  }

  if (!hasSandbox) {
    return (
      <Card title={t("examTemplates.sandbox.gateTitle")} description={t("examTemplates.sandbox.gateBody")}>
        <div className="space-y-4">
          <SampleNote />
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <Select label={t("examTemplates.sandbox.language")} hint={t("examTemplates.sandbox.languageHint")} value={firstLang}
              containerClassName="sm:w-64" onChange={(e) => setFirstLang(e.target.value as Lang)}
              options={LMS_LANGS.map((l) => ({ value: l, label: t(`courses.languages.${l}`) }))} />
            <Button loading={busy} onClick={() => void sync(firstLang)} className="sm:mb-6">{t("examTemplates.sandbox.create")}</Button>
          </div>
          <ExamTemplateError error={error} />
        </div>
      </Card>
    );
  }

  const unsaved = saveState !== "saved" && saveState !== "idle";
  return (
    <div className="space-y-4">
      <SampleNote />
      {unsaved && <p role="status" className="rounded-xl border border-warning-200 bg-warning-50 px-3 py-2 text-sm text-warning-900">{t("examTemplates.sandbox.saveFirst")}</p>}
      {error ? (
        <ExamTemplateError error={error} onRetry={() => void sync()} />
      ) : !sandbox || !course || !assessment ? (
        <LoadingState rows={3} label={t("examTemplates.sandbox.loading")} />
      ) : (
        <>
          <PreviewLauncher draft={draft} languages={assessment.languages} preview={preview} sectionName={sectionName} />
          <CourseContext.Provider value={{ course, reload: reloadCourse, setCourse: setCourseCtx }}>
            <QuizEditor key={editorKey} initial={assessment} mode="sandbox" />
          </CourseContext.Provider>
        </>
      )}
    </div>
  );
}

function SampleNote() {
  const { t } = useTranslation();
  return (
    <p role="note" className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
      <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />{t("examTemplates.sandbox.note")}
    </p>
  );
}

function PreviewLauncher({ draft, languages, preview, sectionName }: {
  draft: SpecDraft;
  languages: Lang[];
  preview: PreviewLaunch;
  sectionName: (i: number) => string;
}) {
  const { lang, t } = useTranslation();
  const { busy, error, issues, params, setParams } = preview;
  const pLang = preview.language && languages.includes(preview.language) ? preview.language : languages.includes(lang) ? lang : languages[0];
  const parameters = previewParameters(draft);
  const notReady = (error as { code?: string } | null)?.code === "preview_not_ready";

  return (
    <Card title={t("examTemplates.preview.title")} description={t("examTemplates.preview.body")}>
      <div className="space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          {languages.length > 1 && (
            <Select label={t("examTemplates.preview.language")} value={pLang} containerClassName="sm:w-48"
              onChange={(e) => preview.setLanguage(e.target.value as Lang)} options={languages.map((l) => ({ value: l, label: t(`courses.languages.${l}`) }))} />
          )}
          {parameters.map((p) => (
            <Select key={p.key} label={t("examTemplates.preview.parameter", { key: p.key })} value={params[p.key] || p.options[0]}
              containerClassName="sm:w-48" onChange={(e) => setParams((x) => ({ ...x, [p.key]: e.target.value }))}
              options={p.options.map((o) => ({ value: o, label: o }))} />
          ))}
          <Button loading={busy} leftIcon={<Eye className="h-4 w-4" aria-hidden="true" />}
            onClick={() => void preview.launch(pLang)}>
            {t("examTemplates.preview.launch")}
          </Button>
        </div>
        {notReady ? <NotReadyCallout issues={issues} sectionName={sectionName} /> : (
          <>
            <ExamTemplateError error={error} />
            {issues.length > 0 && <IssueList issues={issues} kind={error ? "error" : "warning"} />}
          </>
        )}
      </div>
    </Card>
  );
}

const KNOWN_ISSUES = new Set<string>(ISSUE_CODES);

/** `preview_not_ready`: one amber callout, one line per problem, sections named as in the issues bar. */
function NotReadyCallout({ issues, sectionName }: { issues: Issue[]; sectionName: (i: number) => string }) {
  const { t } = useTranslation();
  const lines = Array.from(new Set(issues.map((i) => {
    const text = i.code === "empty_section" ? t("examTemplates.preview.noQuestions")
      : KNOWN_ISSUES.has(i.code) ? t(`assessments.issues.${i.code}`) : t("assessments.issues.unknown", { code: i.code });
    const line = typeof i.section_pos === "number" ? t("examTemplates.preview.issueLine", { section: sectionName(i.section_pos - 1), text }) : text;
    return i.language ? `${line} · ${String(i.language).toUpperCase()}` : line;
  })));
  return (
    <div role="alert" className="rounded-xl border border-warning-200 bg-warning-50 px-3.5 py-3 text-sm text-warning-900">
      <p className="flex items-start gap-2 font-semibold">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />{t("examTemplates.errors.preview_not_ready")}
      </p>
      {lines.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-10">
          {lines.map((l) => <li key={l}>{l}</li>)}
        </ul>
      )}
    </div>
  );
}
