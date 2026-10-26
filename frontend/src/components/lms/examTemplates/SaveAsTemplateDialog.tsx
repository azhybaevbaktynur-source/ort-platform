"use client";

// Phase 7b S4: "Save as template" from the builder (PHASE_7B_DESIGN 5.5, 10): scope the user may use, title, optional
// min/max per section, lock toggle. Creates a DRAFT template (published on the templates page); never changes the exam.
// Not offered for preset (ORT) exams (7b-Q1, P7B-6).
import React, { useEffect, useId, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { saveAsTemplate } from "@/lib/lms/examTemplates";
import { LOCK_SCOPE_KEYS, type ExamTemplateOut, type ExamTemplateScope, type SectionCountsIn } from "@/lib/lms/examTemplateTypes";
import type { AssessmentStaffOut } from "@/lib/lms/assessmentTypes";
import { listMyOrganizations } from "@/lib/lms/organizations";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { cleanLocalized, pickLocalized } from "@/lib/lms/localized";
import type { LocalizedText } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { Button, Dialog, Input, LinkButton, Switch, cn, toast } from "@/components/ui";
import { keyLabel } from "./TemplatePicker";
import { ExamTemplateError } from "./ui";

type Counts = Record<number, { min: string; max: string }>;

/** "" -> null; a whole number 1..10000; anything else NaN. */
const parseCount = (s: string): number | null => {
  const v = s.trim();
  if (!v) return null;
  const n = Number(v);
  return Number.isInteger(n) && n >= 1 && n <= 10000 ? n : Number.NaN;
};

export function SaveAsTemplateDialog({ open, assessment, courseId, onClose }: {
  open: boolean;
  assessment: AssessmentStaffOut;
  courseId: string;
  onClose: () => void;
}) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const { me } = useLmsMe();
  const uid = useId().replace(/:/g, "");
  const a = assessment;
  const orgId = course.organization_id ?? null;
  const [orgAdmin, setOrgAdmin] = useState(false);
  const [scope, setScope] = useState<ExamTemplateScope>("teacher");
  const [title, setTitle] = useState<LocalizedText>({});
  const [counts, setCounts] = useState<Counts>({});
  const [lock, setLock] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [touched, setTouched] = useState(false);
  const [saved, setSaved] = useState<ExamTemplateOut | null>(null);

  useEffect(() => {
    if (!open) return;
    setScope("teacher"); setTitle(a.title ?? {}); setCounts({}); setLock(false); setError(null); setTouched(false); setSaved(null);
    let alive = true;
    if (orgId) {
      listMyOrganizations()
        .then((rows) => { if (alive) setOrgAdmin(rows.some((o) => o.id === orgId && o.role === "org_admin" && o.status === "active")); })
        .catch(() => { if (alive) setOrgAdmin(false); });
    }
    return () => { alive = false; };
  }, [open, a.title, orgId]);

  const scopes: ExamTemplateScope[] = ["teacher", ...(orgAdmin && orgId ? ["organization" as const] : []), ...(me?.is_platform_admin ? ["platform" as const] : [])];
  const cleaned = cleanLocalized(title, course.languages);
  const titleOk = Object.keys(cleaned).length > 0;
  const countErr = (pos: number): string | undefined => {
    const c = counts[pos];
    if (!c) return undefined;
    const mn = parseCount(c.min);
    const mx = parseCount(c.max);
    if (Number.isNaN(mn) || Number.isNaN(mx)) return t("examTemplates.saveAs.countInvalid");
    if (typeof mn === "number" && typeof mx === "number" && mn > mx) return t("examTemplates.saveAs.countOrder");
    return undefined;
  };
  const countsOk = a.sections.every((s) => !countErr(s.position));
  const valid = titleOk && countsOk && !!orgId;

  const setCount = (pos: number, k: "min" | "max", v: string) =>
    setCounts((cur) => ({ ...cur, [pos]: { min: cur[pos]?.min ?? "", max: cur[pos]?.max ?? "", [k]: v } }));

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setTouched(true);
    if (!valid) return;
    setBusy(true);
    setError(null);
    const sections_counts: SectionCountsIn[] = a.sections
      .map((s) => ({ position: s.position, min_items: parseCount(counts[s.position]?.min ?? ""), max_items: parseCount(counts[s.position]?.max ?? "") }))
      .filter((c) => c.min_items !== null || c.max_items !== null);
    try {
      const out = await saveAsTemplate(courseId, a.id, {
        owner_scope: scope,
        organization_id: scope === "platform" ? null : orgId,
        title: cleaned,
        lock_scope: lock ? [...LOCK_SCOPE_KEYS] : [],
        ...(sections_counts.length ? { sections_counts } : {}),
      });
      setSaved(out);
      toast.success(t("examTemplates.saveAs.savedToast"));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const pageHref = (tpl: ExamTemplateOut) => tpl.owner_scope === "platform"
    ? `/${lang}/admin/exam-templates/${tpl.id}`
    : tpl.owner_scope === "organization" && tpl.organization_id
      ? `/${lang}/org/${tpl.organization_id}/exam-templates/${tpl.id}`
      : `/${lang}/exam-templates/${tpl.id}`;

  const formId = `${uid}-form`;
  if (saved) {
    return (
      <Dialog open={open} onClose={onClose} title={t("examTemplates.saveAs.title")} size="md"
        footer={(
          <>
            <Button variant="secondary" onClick={onClose}>{t("ui.close")}</Button>
            <LinkButton href={pageHref(saved)}>{t("examTemplates.saveAs.open")}</LinkButton>
          </>
        )}>
        <p role="status" className="flex items-start gap-2 text-base leading-6 text-slate-800 sm:text-sm">
          <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success-700" aria-hidden="true" />
          <span>{t("examTemplates.saveAs.saved", { title: pickLocalized(saved.title, lang) || t("examTemplates.untitled") })}</span>
        </p>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onClose={onClose} busy={busy} size="lg" title={t("examTemplates.saveAs.title")}
      description={t("examTemplates.saveAs.subtitle")}
      footer={(
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>{t("ui.cancel")}</Button>
          <Button type="submit" form={formId} loading={busy}>{t("examTemplates.saveAs.submit")}</Button>
        </>
      )}>
      <form id={formId} onSubmit={(e) => void submit(e)} className="space-y-5">
        {scopes.length > 1 && (
          <fieldset>
            <legend className="text-sm font-medium leading-6 text-slate-800">{t("examTemplates.saveAs.scope")}</legend>
            <div className="mt-1 space-y-2">
              {scopes.map((s) => (
                <label key={s} className={cn("flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border px-3 py-2.5",
                  scope === s ? "border-brand-500 bg-brand-50" : "border-slate-200 hover:bg-slate-50", "focus-within:ring-2 focus-within:ring-brand-600")}>
                  <input type="radio" name={`${uid}-scope`} className="mt-1 h-4 w-4 accent-brand-600" checked={scope === s} onChange={() => setScope(s)} />
                  <span className="min-w-0">
                    <span className="block font-medium text-slate-900">{t(`examTemplates.scope.${s}`)}</span>
                    <span className="block text-sm leading-5 text-slate-600">{t(`examTemplates.scopeHint.${s}`)}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <div>
          <LocalizedTextInput label={t("examTemplates.fields.title")} languages={course.languages} defaultLanguage={course.default_language}
            value={title} onChange={setTitle} maxLength={200} required />
          {touched && !titleOk && <p className="mt-1 text-sm text-danger-700">{t("examTemplates.fields.titleRequired")}</p>}
        </div>
        {a.sections.length > 0 && (
          <fieldset className="space-y-3">
            <legend className="text-sm font-medium leading-6 text-slate-800">{t("examTemplates.saveAs.counts")}</legend>
            <p className="text-sm text-slate-600">{t("examTemplates.saveAs.countsHint")}</p>
            {a.sections.map((s, i) => {
              const name = pickLocalized(s.title, lang, a.languages[0]) || (s.key ? keyLabel(t, s.key) : t("examTemplates.picker.sectionN", { n: i + 1 }));
              const err = touched ? countErr(s.position) : undefined;
              return (
                <div key={s.id} className="rounded-xl border border-slate-200 p-3">
                  <p className="break-words text-sm font-medium text-slate-900">{i + 1}. {name}</p>
                  <div className="mt-2 grid grid-cols-2 gap-3">
                    <Input label={t("examTemplates.saveAs.min")} inputMode="numeric" optional value={counts[s.position]?.min ?? ""}
                      onChange={(e) => setCount(s.position, "min", e.target.value)} />
                    <Input label={t("examTemplates.saveAs.max")} inputMode="numeric" optional value={counts[s.position]?.max ?? ""}
                      onChange={(e) => setCount(s.position, "max", e.target.value)} />
                  </div>
                  {err && <p className="mt-1 text-sm text-danger-700">{err}</p>}
                </div>
              );
            })}
          </fieldset>
        )}
        <Switch label={t("examTemplates.saveAs.lock")} hint={t("examTemplates.saveAs.lockHint")} checked={lock} onChange={setLock} />
        {!orgId && <p className="text-sm text-danger-700">{t("examTemplates.saveAs.noOrg")}</p>}
        <ExamTemplateError error={error} />
      </form>
    </Dialog>
  );
}
