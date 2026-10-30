"use client";

// Phase 9 S3 (PHASE_9_DESIGN 4.4, 4.11, 8.1, 8.4): roster CSV import in the org area, three steps:
// 1. file (who, target, CSV)  2. check (dry run: masked report, nothing sent)  3. result (after "Confirm and send").
// Students always get invitations (they join themselves); teachers with an account are added directly.
// The page route and the OrgShell nav entry are S2's (org area); this component is self-contained.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Download, FileUp } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listOrgCourses, type OrgCourseOut } from "@/lib/lms/organizations";
import {
  ROSTER_LIMITS, applyRoster, checkRoster, type RosterImport, type RosterImportCounts,
} from "@/lib/lms/invitations";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang, RosterKind, RosterReportRow } from "@/lib/lms/types";
import { Badge, Button, Card, EmptyState, Select, Table, type BadgeTone, type TableColumn } from "@/components/ui";
import { OrgError, apiErrorText } from "./OrgUi";

type T = (key: string, params?: Record<string, string | number>) => string;
type Step = "upload" | "check" | "result";

const OWN_ERRORS = new Set([
  "forbidden_column", "missing_column", "roster_empty", "invalid_csv", "roster_too_large", "file_changed",
  "already_applied", "roster_target_invalid", "student_invitations_disabled", "roster_import_not_found",
]);

const RESULT_TONE: Record<string, BadgeTone> = {
  valid: "info", invited: "success", added: "success", existing_member: "neutral", already_enrolled: "neutral",
  skipped_open_invitation: "neutral", invalid_email: "danger", duplicate_in_file: "warning", failed: "danger",
};

export function rosterErrorText(t: T, error: unknown): string {
  const code = (error as { code?: string } | null)?.code;
  if (code && OWN_ERRORS.has(code)) return t(`rosterImport.errors.${code}`, { rows: ROSTER_LIMITS.rows, kib: ROSTER_LIMITS.kib });
  return apiErrorText(t, error);
}

function RosterError({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (!error) return null;
  const code = (error as { code?: string } | null)?.code;
  if (!code || !OWN_ERRORS.has(code)) return <OrgError error={error} />;
  return (
    <div role="alert" className="rounded-xl border border-danger-200 bg-danger-50 px-3.5 py-3 text-sm text-danger-800">
      {rosterErrorText(t, error)}
    </div>
  );
}

function downloadTemplate(kind: RosterKind) {
  const text = kind === "teacher"
    ? "email;display_name;role\nteacher@example.com;Aigul Asanova;teacher\n"
    : "email;display_name\nstudent@example.com;Bakyt Bekov\n";
  const url = URL.createObjectURL(new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = kind === "teacher" ? "teachers-template.csv" : "students-template.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

function Counts({ counts, applied }: { counts: RosterImportCounts; applied: boolean }) {
  const { t } = useTranslation();
  const tiles: [string, number, BadgeTone][] = applied
    ? [
        ["rosterImport.counts.invited", counts.invited, "success"],
        ["rosterImport.counts.added", counts.added ?? 0, "success"],
        ["rosterImport.counts.existing", counts.existing_member, "neutral"],
        ["rosterImport.counts.skipped", counts.skipped_open_invitation, "neutral"],
        ["rosterImport.counts.invalid", counts.invalid, "danger"],
        ["rosterImport.counts.failed", counts.failed, "danger"],
      ]
    : [
        ["rosterImport.counts.valid", counts.valid, "info"],
        ["rosterImport.counts.existing", counts.existing_member, "neutral"],
        ["rosterImport.counts.skipped", counts.skipped_open_invitation, "neutral"],
        ["rosterImport.counts.invalid", counts.invalid, "danger"],
      ];
  return (
    <ul className="flex flex-wrap gap-2">
      {tiles.filter(([, n], i) => n > 0 || i === 0).map(([key, n, tone]) => (
        <li key={key}><Badge tone={tone}>{t(key, { n })}</Badge></li>
      ))}
    </ul>
  );
}

export function RosterImportWizard({
  orgId, readOnly = false, departments,
}: {
  orgId: string;
  readOnly?: boolean;
  /** Organizations of the tree a teacher import may target (S2's department list); default: this organization. */
  departments?: { id: string; name: string }[];
}) {
  const { lang, t } = useTranslation();
  const [step, setStep] = useState<Step>("upload");
  const [kind, setKind] = useState<RosterKind>("student");
  const [courseId, setCourseId] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [checked, setChecked] = useState<RosterImport | null>(null);
  const [applied, setApplied] = useState<RosterImport | null>(null);
  const [courses, setCourses] = useState<OrgCourseOut[] | null>(null);
  const [moreCourses, setMoreCourses] = useState(false);
  const [coursesError, setCoursesError] = useState<unknown>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const loadCourses = useCallback(async () => {
    setCoursesError(null);
    try {
      const page = await listOrgCourses(orgId, { limit: 100 });
      setCourses(page.items);
      setMoreCourses(!!page.next_cursor);
    } catch (e) {
      setCoursesError(e);
    }
  }, [orgId]);
  useEffect(() => { void loadCourses(); }, [loadCourses]);
  useEffect(() => { headingRef.current?.focus(); }, [step]);

  const courseName = useMemo(() => {
    const c = courses?.find((x) => x.id === (checked?.course_id ?? courseId));
    return c ? pickLocalized(c.title, lang as Lang) : "";
  }, [courses, checked, courseId, lang]);

  const reset = () => {
    setStep("upload"); setFile(null); setChecked(null); setApplied(null); setError(null); setTouched(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const fileError = touched && !file ? t("rosterImport.file.required") : undefined;
  const courseError = touched && kind === "student" && !courseId ? t("rosterImport.course.required") : undefined;

  const check = async (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!file || (kind === "student" && !courseId)) return;
    if (file.size > ROSTER_LIMITS.kib * 1024) { setError({ code: "roster_too_large" }); return; }
    setBusy(true);
    setError(null);
    try {
      const out = await checkRoster(orgId, {
        file, kind, courseId: kind === "student" ? courseId : null,
        departmentId: kind === "teacher" ? departmentId || null : null, language: lang as Lang,
      });
      setChecked(out);
      setStep("check");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    if (!checked || !file) return;
    setBusy(true);
    setError(null);
    try {
      setApplied(await applyRoster(orgId, checked.id, file, lang as Lang));
      setStep("result");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const columns: TableColumn<RosterReportRow>[] = [
    { key: "line", header: t("rosterImport.rows.line"), nowrap: true, cell: (r) => r.line },
    { key: "email", header: t("rosterImport.rows.email"), primary: true, cell: (r) => <span className="[overflow-wrap:anywhere]">{r.email_masked}</span> },
    {
      key: "result", header: t("rosterImport.rows.result"),
      cell: (r) => (
        <span className="flex flex-col items-start gap-1">
          <Badge tone={RESULT_TONE[r.result] ?? "neutral"}>{t(`rosterImport.results.${r.result}`)}</Badge>
          {r.error_code && r.error_code !== r.result && (
            <span className="text-sm text-slate-600">{t(`rosterImport.errorCodes.${r.error_code}`)}</span>
          )}
        </span>
      ),
    },
  ];

  const stepNames: [Step, string][] = [["upload", t("rosterImport.steps.upload")], ["check", t("rosterImport.steps.check")], ["result", t("rosterImport.steps.result")]];
  const stepIndex = stepNames.findIndex(([s]) => s === step);

  const stepper = (
    <ol className="mb-4 flex flex-wrap gap-x-4 gap-y-1 text-sm" aria-label={t("rosterImport.steps.label")}>
      {stepNames.map(([s, label], i) => (
        <li key={s} aria-current={s === step ? "step" : undefined}
          className={i === stepIndex ? "font-semibold text-brand-800" : i < stepIndex ? "text-slate-700" : "text-slate-500"}>
          {i + 1}. {label}
        </li>
      ))}
    </ol>
  );

  if (step === "result" && applied) {
    const partial = applied.status === "partial";
    return (
      <Card as="section" aria-labelledby="roster-step-title">
        {stepper}
        <h2 id="roster-step-title" ref={headingRef} tabIndex={-1} className="mb-3 flex items-center gap-2 text-lg font-semibold text-slate-900 focus:outline-none">
          {!partial && <CheckCircle2 aria-hidden="true" className="h-5 w-5 text-success-700" />}
          {partial ? t("rosterImport.result.partialTitle") : t("rosterImport.result.title")}
        </h2>
        <p className="mb-3 text-sm text-slate-700">
          {partial ? t("rosterImport.result.partial") : applied.kind === "student" ? t("rosterImport.result.students") : t("rosterImport.result.teachers")}
        </p>
        <Counts counts={applied.counts} applied />
        <Table caption={t("rosterImport.rows.caption")} columns={columns} rows={applied.report} rowKey={(r) => String(r.line)} className="mt-4" />
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={reset}>{t("rosterImport.result.again")}</Button>
        </div>
      </Card>
    );
  }

  if (step === "check" && checked) {
    const ready = checked.counts.valid;
    return (
      <Card as="section" aria-labelledby="roster-step-title">
        {stepper}
        <h2 id="roster-step-title" ref={headingRef} tabIndex={-1} className="mb-1 text-lg font-semibold text-slate-900 [overflow-wrap:anywhere] focus:outline-none">
          {t("rosterImport.preview.title", { name: checked.file_name })}
        </h2>
        <p className="mb-3 text-sm text-slate-600">
          {checked.kind === "student" ? t("rosterImport.preview.forCourse", { course: courseName || "—", rows: checked.row_count }) : t("rosterImport.preview.forTeachers", { rows: checked.row_count })}
        </p>
        <Counts counts={checked.counts} applied={false} />
        {checked.ignored_columns.length > 0 && (
          <p className="mt-3 text-sm text-slate-600">{t("rosterImport.preview.ignored", { list: checked.ignored_columns.join(", ") })}</p>
        )}
        <p className="mt-3 text-sm text-slate-700">{checked.kind === "student" ? t("rosterImport.preview.studentsNote") : t("rosterImport.preview.teachersNote")}</p>
        <Table caption={t("rosterImport.rows.caption")} columns={columns} rows={checked.report} rowKey={(r) => String(r.line)} className="mt-4" />
        {error ? <div className="mt-4"><RosterError error={error} /></div> : null}
        {ready === 0 && <p className="mt-4 text-sm font-medium text-slate-800">{t("rosterImport.preview.nothing")}</p>}
        <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" disabled={busy} onClick={reset}>{t("rosterImport.preview.back")}</Button>
          <Button loading={busy} disabled={readOnly || ready === 0} onClick={() => void apply()}>
            {t("rosterImport.preview.apply", { n: ready })}
          </Button>
        </div>
      </Card>
    );
  }

  const courseOptions = (courses ?? []).map((c) => ({ value: c.id, label: pickLocalized(c.title, lang as Lang) || c.id }));
  return (
    <Card as="section" aria-labelledby="roster-step-title">
      {stepper}
      <h2 id="roster-step-title" ref={headingRef} tabIndex={-1} className="mb-1 text-lg font-semibold text-slate-900 focus:outline-none">{t("rosterImport.title")}</h2>
      <p className="mb-4 text-sm text-slate-600">{t("rosterImport.intro")}</p>
      <form onSubmit={check} noValidate className="space-y-4">
        <Select id="roster-kind" label={t("rosterImport.kind.label")} value={kind} disabled={busy}
          onChange={(e) => { setKind(e.target.value as RosterKind); setError(null); }}
          options={[{ value: "student", label: t("rosterImport.kind.student") }, { value: "teacher", label: t("rosterImport.kind.teacher") }]} />
        {kind === "student" ? (
          coursesError ? <OrgError error={coursesError} onRetry={() => void loadCourses()} />
          : courses && courses.length === 0 ? <EmptyState title={t("rosterImport.course.none")} />
          : (
            <Select id="roster-course" label={t("rosterImport.course.label")} value={courseId} disabled={busy || courses === null}
              placeholder={t("rosterImport.course.placeholder")} options={courseOptions} error={courseError}
              hint={moreCourses ? t("rosterImport.course.more") : t("rosterImport.course.hint")}
              onChange={(e) => setCourseId(e.target.value)} />
          )
        ) : departments && departments.length > 0 ? (
          <Select id="roster-dept" label={t("rosterImport.department.label")} value={departmentId} disabled={busy}
            options={[{ value: "", label: t("rosterImport.department.self") }, ...departments.map((d) => ({ value: d.id, label: d.name }))]}
            onChange={(e) => setDepartmentId(e.target.value)} />
        ) : null}

        <div>
          {/* Phase 9 UX: a hidden file input behind a design-system Button, with the chosen file's name */}
          <p id="roster-file-label" className="mb-1.5 block text-sm font-medium text-slate-900">{t("rosterImport.file.label")}</p>
          <input id="roster-file" ref={fileRef} type="file" accept=".csv,text/csv" disabled={busy} tabIndex={-1}
            aria-labelledby="roster-file-label" className="sr-only"
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); setError(null); }} />
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
            <Button id="roster-file-button" type="button" variant="secondary" disabled={busy}
              aria-labelledby="roster-file-label roster-file-button" aria-describedby="roster-file-name roster-file-hint"
              aria-invalid={fileError ? true : undefined}
              onClick={() => fileRef.current?.click()}>
              {t("rosterImport.file.choose")}
            </Button>
            <span id="roster-file-name" className={`min-w-0 break-all text-sm ${file ? "font-medium text-slate-900" : "text-slate-600"}`}>
              {file ? file.name : t("rosterImport.file.none")}
            </span>
          </div>
          <p id="roster-file-hint" className="mt-1.5 text-sm text-slate-600">{t("rosterImport.file.hint", { rows: ROSTER_LIMITS.rows, kib: ROSTER_LIMITS.kib })}</p>
          {fileError && <p role="alert" className="mt-1.5 text-sm text-danger-700">{fileError}</p>}
        </div>

        <details className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
          <summary className="cursor-pointer font-medium text-slate-900">{t("rosterImport.help.title")}</summary>
          <div className="mt-2 space-y-2">
            <p>{kind === "teacher" ? t("rosterImport.help.teachers") : t("rosterImport.help.students")}</p>
            <p>{t("rosterImport.help.header")}</p>
            <p>{t("rosterImport.help.noPassword")}</p>
            <pre className="overflow-x-auto rounded-lg bg-white p-2 text-xs text-slate-800">{kind === "teacher" ? "email;display_name;role\nteacher@example.com;Aigul Asanova;teacher" : "email;display_name\nstudent@example.com;Bakyt Bekov"}</pre>
            <Button variant="secondary" size="sm" leftIcon={<Download aria-hidden="true" className="h-4 w-4" />} onClick={() => downloadTemplate(kind)}>
              {t("rosterImport.help.template")}
            </Button>
          </div>
        </details>

        <RosterError error={error} />
        <div className="flex justify-end">
          <Button type="submit" loading={busy} disabled={readOnly} leftIcon={<FileUp aria-hidden="true" className="h-4 w-4" />}>
            {t("rosterImport.check")}
          </Button>
        </div>
      </form>
    </Card>
  );
}
