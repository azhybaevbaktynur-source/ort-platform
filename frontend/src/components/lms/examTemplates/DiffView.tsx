"use client";

// Phase 8b S4: the computed difference between two template versions, or a version and the draft
// (`GET /exam-templates/{id}/diff`, PHASE_8B_DESIGN 5.2, 9.1). Summary chips, then the changes grouped as General,
// Sections, Parameters and Locks; before/after side by side from `lg:`, stacked rows below.
import React, { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { getTemplateDiff } from "@/lib/lms/examTemplates";
import type { BlocksOut, SpecChange, SpecDiffEnd, SpecDiffOut } from "@/lib/lms/examTemplateTypes";
import { questionTypeTitleKey } from "@/lib/lms/blocks";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { Badge, Card, IconButton, LoadingState, cn, type BadgeTone } from "@/components/ui";
import { DEFAULT_FIELDS, ExamTemplateError, PARAM_FIELDS, SECTION_FIELDS, TOP_FIELDS } from "./ui";
import { schemeTitle } from "./ScoringTab";
import { passageDisplayLabel } from "./SectionList";
import { minText } from "./specDraft";

type T = (k: string, p?: Record<string, string | number>) => string;
type Group = "common" | "sections" | "parameters" | "locks";
const GROUPS: Group[] = ["common", "sections", "parameters", "locks"];
const SECTION_RE = /^sections\[([^\]]+)\](?:\.(.+))?$/;
const PARAM_RE = /^parameters\[([^\]]+)\](?:\.(.+))?$/;
const KIND_TONE: Record<SpecChange["kind"], BadgeTone> = { added: "success", removed: "danger", changed: "info" };

function groupOf(path: string): Group {
  if (path === "lock_scope" || path.startsWith("lock_scope")) return "locks";
  if (path.startsWith("sections")) return "sections";
  if (path.startsWith("parameters")) return "parameters";
  return "common";
}

const isLocalized = (v: unknown): v is LocalizedText =>
  !!v && typeof v === "object" && !Array.isArray(v) && Object.values(v as object).every((x) => typeof x === "string");

/** One value in the user's words (labels from the block catalog and the i18n files; never raw JSON when avoidable). */
function useValueText(blocks: BlocksOut | null) {
  const { lang, t } = useTranslation();
  const fmt = (field: string, v: unknown): string => {
    if (v === null || v === undefined || v === "") {
      return field === "passage_display" || field === "result_view" ? t("examTemplates.editor.courseDefault") : "—";
    }
    if (typeof v === "boolean") return t(v ? "examTemplates.diff.yes" : "examTemplates.diff.no");
    if (Array.isArray(v)) {
      if (!v.length) return "—";
      if (field === "allowed_types") return v.map((q) => t(blocks?.question_types.find((x) => x.key === q)?.title_key ?? questionTypeTitleKey(String(q)))).join(", ");
      if (field === "lock_scope") return v.map((k) => t(`examTemplates.specForm.lockKeys.${k}`)).join(", ");
      return v.map((x) => (typeof x === "object" ? fmtObject(x) : String(x))).join(", ");
    }
    if (typeof v === "object") return fmtObject(v);
    const s = String(v);
    switch (field) {
      case "navigation": return t(`assessments.navigation.${s}`);
      case "display_mode": return t(`examTemplates.blocks.displayModes.${s}`);
      case "passage_display": return passageDisplayLabel(t, s);
      case "result_view": return t(`examTemplates.blocks.resultViews.${s}`);
      case "score_policy": return t(`assessments.scorePolicy.${s}`);
      case "results_policy": return t(`assessments.results.${s}`);
      case "time_limit_s": return t("examTemplates.picker.minutes", { n: minText(Number(s)) });
      case "allowed_attempts": return s === "-1" ? t("assessments.settings.unlimited") : s;
      case "grading_scheme_version_id": {
        const b = blocks?.scheme_versions.find((x) => x.id === s);
        return b ? schemeTitle(b, lang as Lang) : t("examTemplates.diff.otherScheme");
      }
      default: return s;
    }
  };
  const fmtObject = (v: object): string => {
    if (isLocalized(v)) return pickLocalized(v, lang) || "—";
    const o = v as Record<string, unknown>;
    if ("grading_scheme_version_id" in o) return fmt("grading_scheme_version_id", o.grading_scheme_version_id);
    if ("allowed_types" in o) {
      const title = isLocalized(o.title) ? pickLocalized(o.title, lang) : "";
      return [title || (o.key ? String(o.key) : ""), fmt("allowed_types", o.allowed_types)].filter(Boolean).join(" · ");
    }
    if ("options" in o && "key" in o) return `${String(o.key)}: ${fmt("options", o.options)}`;
    return JSON.stringify(v);
  };
  return fmt;
}

function sectionLabel(c: SpecChange, ref: string, lang: Lang, t: T): string {
  const s = c.section;
  const title = s?.title ? pickLocalized(s.title, lang) : "";
  if (title) return title;
  if (s?.key) return t("examTemplates.diff.sectionKey", { key: s.key });
  if (s && typeof s.position === "number") return t("examTemplates.picker.sectionN", { n: s.position + 1 });
  return /^\d+$/.test(ref) ? t("examTemplates.picker.sectionN", { n: Number(ref) + 1 }) : ref;
}

/** "What changed" label of one change, and the field name used to format its values. */
function describe(c: SpecChange, lang: Lang, t: T): { where: string | null; what: string; field: string } {
  const sm = SECTION_RE.exec(c.path);
  if (sm) {
    const [, ref, field] = sm;
    const where = sectionLabel(c, ref, lang, t);
    if (!field) return { where, what: t(c.kind === "added" ? "examTemplates.diff.sectionAdded" : c.kind === "removed" ? "examTemplates.diff.sectionRemoved" : "examTemplates.diff.sectionChanged"), field: "section" };
    return { where, what: SECTION_FIELDS[field] ? t(SECTION_FIELDS[field]) : field, field };
  }
  const pm = PARAM_RE.exec(c.path);
  if (pm) {
    const [, ref, field] = pm;
    const where = t("examTemplates.diff.parameter", { key: ref });
    if (!field) return { where, what: t(c.kind === "added" ? "examTemplates.diff.parameterAdded" : c.kind === "removed" ? "examTemplates.diff.parameterRemoved" : "examTemplates.diff.sectionChanged"), field: "parameter" };
    return { where, what: PARAM_FIELDS[field] ? t(PARAM_FIELDS[field]) : field, field };
  }
  const parts = c.path.split(".");
  if (parts[0] === "defaults" && parts[1]) return { where: t(TOP_FIELDS.defaults), what: DEFAULT_FIELDS[parts[1]] ? t(DEFAULT_FIELDS[parts[1]]) : parts[1], field: parts[1] };
  if (parts[0] === "scoring") return { where: null, what: t(TOP_FIELDS.scoring), field: "grading_scheme_version_id" };
  return { where: null, what: TOP_FIELDS[parts[0]] ? t(TOP_FIELDS[parts[0]]) : c.path, field: parts[0] };
}

export function DiffView({ templateId, from, to, blocks, onClose }: {
  templateId: string;
  from: SpecDiffEnd;
  to: SpecDiffEnd;
  blocks: BlocksOut | null;
  onClose: () => void;
}) {
  const { lang, t } = useTranslation();
  const [diff, setDiff] = useState<SpecDiffOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const fmt = useValueText(blocks);

  useEffect(() => {
    let alive = true;
    setDiff(null);
    setError(null);
    getTemplateDiff(templateId, from, to)
      .then((d) => { if (alive) setDiff(d); })
      .catch((e) => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [templateId, from, to, attempt]);

  const end = (x: SpecDiffEnd) => (x === "draft" ? t("examTemplates.diff.draft") : t("examTemplates.versionShort", { n: x }));
  const title = t("examTemplates.diff.title", { from: end(from), to: end(to) });
  const s = diff?.summary;
  const chips = s ? [
    { n: s.sections_added, key: "sectionsAdded" },
    { n: s.sections_removed, key: "sectionsRemoved" },
    { n: s.sections_changed, key: "sectionsChanged" },
    { n: s.fields_changed, key: "fieldsChanged" },
  ].filter((c) => c.n > 0) : [];

  return (
    <Card id="tpl-diff" title={title} actions={<IconButton aria-label={t("examTemplates.diff.close")} icon={<X className="h-4 w-4" aria-hidden="true" />} onClick={onClose} />}>
      {error ? <ExamTemplateError error={error} onRetry={() => setAttempt((n) => n + 1)} />
        : !diff ? <LoadingState rows={3} label={t("lms.common.loading")} />
          : diff.changes.length === 0 ? <p className="text-sm text-slate-600">{t("examTemplates.diff.noChanges")}</p>
            : (
              <div className="space-y-5">
                {chips.length > 0 && (
                  <ul className="flex flex-wrap gap-2" aria-label={t("examTemplates.diff.summaryLabel")}>
                    {chips.map((c) => <li key={c.key}><Badge tone="neutral">{t(`examTemplates.diff.summary.${c.key}`, { n: c.n })}</Badge></li>)}
                  </ul>
                )}
                <div className="hidden grid-cols-[minmax(0,14rem)_minmax(0,1fr)_minmax(0,1fr)] gap-x-4 border-b border-slate-200 pb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 lg:grid">
                  <span>{t("examTemplates.diff.field")}</span><span>{end(from)}</span><span>{end(to)}</span>
                </div>
                {GROUPS.map((g) => {
                  const rows = diff.changes.filter((c) => groupOf(c.path) === g);
                  if (!rows.length) return null;
                  return (
                    <section key={g} aria-labelledby={`tpl-diff-${g}`} className="space-y-2">
                      <h3 id={`tpl-diff-${g}`} className="text-base font-semibold text-slate-900">{t(`examTemplates.diff.groups.${g}`)}</h3>
                      <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
                        {rows.map((c, idx) => {
                          const d = describe(c, lang as Lang, t);
                          const whole = d.field === "section" || d.field === "parameter";
                          const before = c.kind === "added" ? "—" : fmt(d.field, c.before);
                          const after = c.kind === "removed" ? "—" : fmt(d.field, c.after);
                          return (
                            <li key={`${c.path}-${idx}`} className="grid grid-cols-1 gap-2 px-3 py-2.5 lg:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_minmax(0,1fr)] lg:gap-x-4">
                              <div className="min-w-0">
                                {d.where && <p className="break-words text-xs font-medium text-slate-600">{d.where}</p>}
                                <p className="break-words text-sm font-medium text-slate-900">{d.what}</p>
                                <Badge tone={KIND_TONE[c.kind]} className="mt-1">{t(`examTemplates.diff.${c.kind}`)}</Badge>
                              </div>
                              <DiffValue label={end(from)} value={before} tone={c.kind === "added" ? "muted" : "before"} whole={whole} />
                              <DiffValue label={end(to)} value={after} tone={c.kind === "removed" ? "muted" : "after"} whole={whole} />
                              {g === "locks" && Array.isArray(c.before) && Array.isArray(c.after) && <LockDelta before={c.before} after={c.after} />}
                            </li>
                          );
                        })}
                      </ul>
                    </section>
                  );
                })}
              </div>
            )}
    </Card>
  );
}

function DiffValue({ label, value, tone, whole }: { label: string; value: string; tone: "before" | "after" | "muted"; whole: boolean }) {
  return (
    <div className="flex min-w-0 items-start gap-2 lg:block">
      <span className="w-16 shrink-0 text-xs font-semibold uppercase tracking-wide text-slate-500 lg:hidden">{label}</span>
      <span className={cn("min-w-0 break-words rounded-lg px-2 py-1 text-sm",
        tone === "before" && "bg-danger-50 text-danger-900", tone === "after" && "bg-success-50 text-success-900", tone === "muted" && "text-slate-500",
        whole && tone !== "muted" && "block")}>
        {value}
      </span>
    </div>
  );
}

function LockDelta({ before, after }: { before: unknown[]; after: unknown[] }) {
  const { t } = useTranslation();
  const added = after.filter((k) => !before.includes(k));
  const removed = before.filter((k) => !after.includes(k));
  const label = (k: unknown) => t(`examTemplates.specForm.lockKeys.${String(k)}`);
  return (
    <p className="flex flex-wrap items-center gap-x-2 text-sm text-slate-700 lg:col-span-3">
      {added.length > 0 && <span>{t("examTemplates.diff.locksAdded", { keys: added.map(label).join(", ") })}</span>}
      {removed.length > 0 && <span>{t("examTemplates.diff.locksRemoved", { keys: removed.map(label).join(", ") })}</span>}
    </p>
  );
}
