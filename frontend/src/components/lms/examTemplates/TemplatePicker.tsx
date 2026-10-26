"use client";

// Phase 7b S4: "Start from" in the create dialogs (PHASE_7B_DESIGN 10): Blank + the exam templates visible in the
// course (grouped platform / organization / mine), a read-only section summary and one select per parameter.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { getExamTemplateVersion, listExamTemplates } from "@/lib/lms/examTemplates";
import type { ExamTemplateOut, ExamTemplateScope, ExamTemplateSpec, SpecSection, TemplateCreateFields } from "@/lib/lms/examTemplateTypes";
import { questionTypeTitleKey } from "@/lib/lms/blocks";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { Select, Skeleton } from "@/components/ui";
import { ExamTemplateError } from "./ui";

type T = (k: string, p?: Record<string, string | number>) => string;

/** Label of a section key or parameter option: `sections.<key>` when translated, else the key itself. */
export function keyLabel(t: T, key: string): string {
  const k = `sections.${key}`;
  const v = t(k);
  return v === k ? key : v;
}

export function sectionLabel(t: T, lang: Lang, s: SpecSection, i: number, boundValue?: string): string {
  const title = pickLocalized(s.title ?? null, lang);
  if (title) return title;
  const key = s.key ?? boundValue;
  if (key) return keyLabel(t, key);
  return t("examTemplates.picker.sectionN", { n: i + 1 });
}

/** Index of the section a parameter binds (`sections[<i>].key`). */
export function boundIndex(binds: string): number | null {
  const m = /^sections\[(\d+)\]\.key$/.exec(binds);
  return m ? Number(m[1]) : null;
}

export interface TemplatePickerState {
  templates: ExamTemplateOut[];
  loading: boolean;
  error: unknown;
  reload: () => void;
  selectedId: string;
  select: (id: string) => void;
  selected: ExamTemplateOut | null;
  spec: ExamTemplateSpec | null;
  specLoading: boolean;
  specError: unknown;
  parameters: Record<string, string>;
  setParameter: (key: string, value: string) => void;
  /** True when a template is chosen (the preset radios are hidden then). */
  active: boolean;
  /** Ready to submit: blank, or a template whose spec loaded and every parameter is chosen. */
  valid: boolean;
  /** Body fields for the create request (empty object for "Blank"). */
  fields: () => TemplateCreateFields;
}

/** Loads the picker list when `open` turns true (one page of up to 100 published templates visible in the course). */
export function useTemplatePicker(courseId: string, open: boolean): TemplatePickerState {
  const [templates, setTemplates] = useState<ExamTemplateOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [selectedId, setSelectedId] = useState("");
  const [spec, setSpec] = useState<ExamTemplateSpec | null>(null);
  const [specLoading, setSpecLoading] = useState(false);
  const [specError, setSpecError] = useState<unknown>(null);
  const [parameters, setParameters] = useState<Record<string, string>>({});
  const gen = useRef(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await listExamTemplates({ course_id: courseId, status: "published", limit: 100 });
      setTemplates(page.items);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    if (!open) return;
    setSelectedId(""); setSpec(null); setSpecError(null); setParameters({});
    void load();
  }, [open, load]);

  const selected = useMemo(() => templates.find((x) => x.id === selectedId) ?? null, [templates, selectedId]);

  const loadSpec = useCallback(async (tpl: ExamTemplateOut) => {
    const my = ++gen.current;
    setSpec(null);
    setSpecError(null);
    setParameters({});
    if (tpl.current_spec) { setSpec(tpl.current_spec); return; }
    if (tpl.current_version_no == null) { setSpecError({ code: "template_not_published" }); return; }
    setSpecLoading(true);
    try {
      const v = await getExamTemplateVersion(tpl.id, tpl.current_version_no);
      if (my === gen.current) setSpec(v.spec);
    } catch (e) {
      if (my === gen.current) setSpecError(e);
    } finally {
      if (my === gen.current) setSpecLoading(false);
    }
  }, []);

  const select = useCallback((id: string) => {
    setSelectedId(id);
    const tpl = templates.find((x) => x.id === id);
    if (tpl) void loadSpec(tpl);
    else { gen.current++; setSpec(null); setSpecError(null); setSpecLoading(false); setParameters({}); }
  }, [templates, loadSpec]);

  const setParameter = useCallback((key: string, value: string) => setParameters((cur) => ({ ...cur, [key]: value })), []);

  const active = !!selected;
  const params = spec?.parameters ?? [];
  const valid = !active || (!!spec && params.every((p) => !!parameters[p.key]));
  const fields = useCallback((): TemplateCreateFields => {
    if (!selected) return {};
    return { exam_template_id: selected.id, ...(params.length ? { parameters } : {}) };
  }, [selected, params.length, parameters]);

  return {
    templates, loading, error, reload: () => void load(), selectedId, select, selected, spec, specLoading, specError,
    parameters, setParameter, active, valid, fields,
  };
}

const GROUPS: ExamTemplateScope[] = ["platform", "organization", "teacher"];

export function TemplatePicker({ picker, disabled }: { picker: TemplatePickerState; disabled?: boolean }) {
  const { lang, t } = useTranslation();
  const p = picker;
  const title = (x: ExamTemplateOut) => {
    const name = pickLocalized(x.title, lang) || t("examTemplates.untitled");
    return x.current_version_no != null ? `${name} · ${t("examTemplates.versionShort", { n: x.current_version_no })}` : name;
  };
  const grouped = GROUPS.map((g) => ({ g, rows: p.templates.filter((x) => x.owner_scope === g) })).filter((x) => x.rows.length > 0);
  const empty = !p.loading && !p.error && p.templates.length === 0;

  return (
    <div className="space-y-3">
      <Select label={t("examTemplates.picker.startFrom")} value={p.selectedId} disabled={disabled || p.loading}
        onChange={(e) => p.select(e.target.value)}
        hint={p.loading ? t("examTemplates.picker.loading") : empty ? t("examTemplates.picker.none") : t("examTemplates.picker.hint")}>
        <option value="">{t("examTemplates.picker.blank")}</option>
        {grouped.map(({ g, rows }) => (
          <optgroup key={g} label={t(`examTemplates.picker.group.${g}`)}>
            {rows.map((x) => <option key={x.id} value={x.id}>{title(x)}</option>)}
          </optgroup>
        ))}
      </Select>
      <ExamTemplateError error={p.error} onRetry={p.reload} />
      {p.active && <TemplateSummary picker={p} disabled={disabled} />}
    </div>
  );
}

function TemplateSummary({ picker, disabled }: { picker: TemplatePickerState; disabled?: boolean }) {
  const { lang, t } = useTranslation();
  const { spec, specLoading, specError, parameters, setParameter } = picker;
  if (specLoading) return <div role="status" aria-label={t("lms.common.loading")} className="space-y-2"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-5 w-1/2" /></div>;
  if (specError) return <ExamTemplateError error={specError} onRetry={() => picker.selected && picker.select(picker.selected.id)} />;
  if (!spec) return null;
  const params = spec.parameters ?? [];
  const bound = new Map<number, string>();
  for (const prm of params) {
    const i = boundIndex(prm.binds);
    if (i !== null && parameters[prm.key]) bound.set(i, parameters[prm.key]);
  }
  return (
    <div className="space-y-3">
      {params.map((prm) => (
        <Select key={prm.key} label={t("examTemplates.picker.parameter", { key: keyLabel(t, prm.key) })} value={parameters[prm.key] ?? ""}
          disabled={disabled} placeholder={t("examTemplates.picker.choose")} onChange={(e) => setParameter(prm.key, e.target.value)}
          options={prm.options.map((o) => ({ value: o, label: keyLabel(t, o) }))} />
      ))}
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5">
        <p className="text-sm font-medium text-slate-800">{t("examTemplates.picker.sections", { n: spec.sections.length })}</p>
        <ol className="mt-1 space-y-1.5 text-sm text-slate-700">
          {spec.sections.map((s, i) => (
            <li key={i} className="break-words">
              <span className="font-medium text-slate-900">{i + 1}. {sectionLabel(t, lang, s, i, bound.get(i))}</span>
              <span className="block text-slate-600">
                {s.allowed_types.map((ty) => t(questionTypeTitleKey(ty))).join(", ")}
                {countText(t, s.min_items, s.max_items)}
                {s.time_limit_s ? ` · ${t("examTemplates.picker.minutes", { n: Math.round(s.time_limit_s / 60) })}` : ""}
              </span>
            </li>
          ))}
        </ol>
        <p className="mt-2 text-sm text-slate-600">{t("examTemplates.picker.after")}</p>
      </div>
    </div>
  );
}

export function countText(t: T, min?: number | null, max?: number | null): string {
  if (min && max) return ` · ${t("examTemplates.counts.range", { min, max })}`;
  if (min) return ` · ${t("examTemplates.counts.min", { min })}`;
  if (max) return ` · ${t("examTemplates.counts.max", { max })}`;
  return "";
}
