"use client";

// Phase 8b S4: Sample questions tab (PHASE_8B_DESIGN 7, 9.1). `SandboxGate` creates (or syncs) the template's hidden
// sandbox course + sample quiz with `POST /exam-templates/{id}/sandbox`, then mounts the 7c card editor on it
// (`QuizEditor mode="sandbox"` under a CourseContext built from `GET /courses/{sandbox}`). `PreviewLauncher` starts
// a staff preview attempt and opens the real general player with `?return=` back here (new tab at lg:, same tab
// below). The server syncs the sample from the *stored* draft, so unsaved constructor changes are flushed first.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Eye, FlaskConical, Info } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { ensureTemplateSandbox, startTemplatePreview } from "@/lib/lms/examTemplates";
import type { ExamTemplateOut, SandboxOut } from "@/lib/lms/examTemplateTypes";
import { getCourse } from "@/lib/lms/courses";
import { getAssessment } from "@/lib/lms/assessments";
import { isStaffAssessment, type AssessmentStaffOut, type Issue } from "@/lib/lms/assessmentTypes";
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

export function SampleTab({ tpl, draft, active, archived, saveState, flush }: {
  tpl: ExamTemplateOut;
  draft: SpecDraft;
  /** The tab is visible: (re)sync when the stored draft changed since the last sync. */
  active: boolean;
  archived: boolean;
  saveState: SaveState;
  flush: () => Promise<boolean>;
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
      setCourse(c);
      setAssessment(a);
      setEditorKey((k) => k + 1);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }, [tpl.id, flush]);

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
          <PreviewLauncher tpl={tpl} draft={draft} languages={assessment.languages} flush={flush} />
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

function PreviewLauncher({ tpl, draft, languages, flush }: {
  tpl: ExamTemplateOut;
  draft: SpecDraft;
  languages: Lang[];
  flush: () => Promise<boolean>;
}) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const pathname = usePathname();
  const [pLang, setPLang] = useState<Lang>(languages.includes(lang) ? lang : languages[0]);
  const [params, setParams] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const parameters = draft.parameters
    .map((p) => ({ key: p.key.trim(), options: splitOptions(p.options) }))
    .filter((p) => p.key && p.options.length);

  const launch = async () => {
    // a new tab must be opened inside the click (popup blockers); it is pointed at the player once the attempt exists
    const wide = typeof window !== "undefined" && window.matchMedia(NEW_TAB_QUERY).matches;
    const win = wide ? window.open("", "_blank") : null;
    setBusy(true);
    setError(null);
    setIssues([]);
    try {
      await flush();
      const chosen = Object.fromEntries(parameters.map((p) => [p.key, params[p.key] || p.options[0]]));
      const out = await startTemplatePreview(tpl.id, { language: pLang, ...(parameters.length ? { parameters: chosen } : {}) });
      setIssues((out.issues ?? []) as unknown as Issue[]);
      const back = `${pathname}?tab=sample`;
      const url = `/${lang}/courses/${out.course_id}/attempts/${out.attempt_id}?return=${encodeURIComponent(back)}`;
      if (win) { win.opener = null; win.location.href = url; } else router.push(url);
    } catch (e) {
      win?.close();
      setError(e);
      setIssues(issuesFromDetails((e as { details?: unknown }).details));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title={t("examTemplates.preview.title")} description={t("examTemplates.preview.body")}>
      <div className="space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          {languages.length > 1 && (
            <Select label={t("examTemplates.preview.language")} value={pLang} containerClassName="sm:w-48"
              onChange={(e) => setPLang(e.target.value as Lang)} options={languages.map((l) => ({ value: l, label: t(`courses.languages.${l}`) }))} />
          )}
          {parameters.map((p) => (
            <Select key={p.key} label={t("examTemplates.preview.parameter", { key: p.key })} value={params[p.key] || p.options[0]}
              containerClassName="sm:w-48" onChange={(e) => setParams((x) => ({ ...x, [p.key]: e.target.value }))}
              options={p.options.map((o) => ({ value: o, label: o }))} />
          ))}
          <Button loading={busy} leftIcon={<Eye className="h-4 w-4" aria-hidden="true" />} onClick={() => void launch()}>
            {t("examTemplates.preview.launch")}
          </Button>
        </div>
        <ExamTemplateError error={error} />
        {issues.length > 0 && <IssueList issues={issues} kind={error ? "error" : "warning"} />}
      </div>
    </Card>
  );
}
