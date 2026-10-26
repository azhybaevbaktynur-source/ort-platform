"use client";

// Phase 7b S7 (UX fix, blocker): the template structure as a form instead of a JSON field. Defaults, a repeatable
// section card list (add / remove / move; key from the title, editable under "Advanced"), parameters (only when the
// spec has them), lock scope checkboxes, and the raw JSON behind a collapsed disclosure for the platform admin.
// Server issues (`spec_invalid`) show under the matching field.
import React, { useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { LOCK_SCOPE_KEYS, type BlocksOut, type ExamTemplateSpec, type LockScopeKey, type SpecIssue } from "@/lib/lms/examTemplateTypes";
import { PASSAGE_DISPLAYS, QUESTION_TYPES, passageRenderers, questionTypeTitleKey } from "@/lib/lms/blocks";
import { RESULTS_POLICIES, SCORE_POLICIES, type ResultsPolicy, type ScorePolicy } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { LMS_LANGS, type Lang } from "@/lib/lms/types";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { Button, Card, Checkbox, FieldError, IconButton, Input, Select, Textarea, toast } from "@/components/ui";
import {
  boundSections, draftOf, keyFromTitle, keySourceTitle, newParameter, newSection, sectionKey, specOf,
  type DefaultsDraft, type ParameterDraft, type SectionDraft, type SpecDraft,
} from "./specDraft";
import { locStartsWith, useSpecIssueText } from "./ui";

type Update = (fn: (d: SpecDraft) => SpecDraft) => void;

/** Translated issues whose `loc` starts with `prefix` (one line each, under the field). */
function useFieldIssues(issues: SpecIssue[], what: (i: SpecIssue) => string) {
  return (...prefix: (string | number)[]): string | undefined => {
    const hit = issues.filter((i) => locStartsWith(i.loc, prefix) && (prefix.length > 1 || i.loc.length <= 1));
    return hit.length ? Array.from(new Set(hit.map(what))).join(" ") : undefined;
  };
}

export function SpecForm({ draft, update, readOnly, issues, blocks, platform, sectionName }: {
  draft: SpecDraft;
  update: Update;
  readOnly: boolean;
  issues: SpecIssue[];
  blocks: BlocksOut | null;
  /** Platform admin area: the raw JSON disclosure is offered. */
  platform: boolean;
  sectionName: (index: number) => string;
}) {
  const { t } = useTranslation();
  const { what } = useSpecIssueText(sectionName);
  const err = useFieldIssues(issues, what);
  const types = blocks?.question_types?.length ? blocks.question_types.map((q) => q.key) : [...QUESTION_TYPES];
  const bound = boundSections(draft);

  const setDefaults = (patch: Partial<DefaultsDraft>) => update((d) => ({ ...d, defaults: { ...d.defaults, ...patch } }));
  const setSection = (uid: string, patch: Partial<SectionDraft>) =>
    update((d) => ({ ...d, sections: d.sections.map((s) => (s.uid === uid ? { ...s, ...patch } : s)) }));
  const move = (i: number, by: number) => update((d) => {
    const next = [...d.sections];
    const [s] = next.splice(i, 1);
    next.splice(i + by, 0, s);
    return { ...d, sections: next };
  });
  // a removed section takes the parameter that supplied its key with it
  const remove = (uid: string) => update((d) => ({
    ...d, sections: d.sections.filter((s) => s.uid !== uid), parameters: d.parameters.filter((p) => p.section !== uid),
  }));
  const add = () => update((d) => ({ ...d, sections: [...d.sections, newSection(types.filter((x) => x !== "comparison"))] }));
  const setParam = (uid: string, patch: Partial<ParameterDraft>) =>
    update((d) => ({ ...d, parameters: d.parameters.map((p) => (p.uid === uid ? { ...p, ...patch } : p)) }));
  const toggleLock = (k: LockScopeKey) =>
    update((d) => ({ ...d, lockScope: d.lockScope.includes(k) ? d.lockScope.filter((x) => x !== k) : [...d.lockScope, k] }));

  const d = draft.defaults;
  const forward = draft.navigation === "section_forward_only";
  const showParams = (draft.base.parameters?.length ?? 0) > 0 || draft.parameters.length > 0;

  return (
    <>
      <Card className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{t("examTemplates.specForm.defaults")}</h2>
          <p className="mt-1 text-sm text-slate-600">{t("examTemplates.specForm.defaultsHint")}</p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input label={t("examTemplates.specForm.totalTime")} inputMode="decimal" value={d.timeMin} disabled={readOnly}
            hint={t("examTemplates.specForm.totalTimeHint")} error={err("defaults", "time_limit_s")}
            onChange={(e) => setDefaults({ timeMin: e.target.value })} />
          <div>
            <Input label={t("assessments.settings.attempts")} inputMode="numeric" value={d.attempts} disabled={readOnly || d.unlimited}
              error={err("defaults", "allowed_attempts")} onChange={(e) => setDefaults({ attempts: e.target.value })} />
            <Checkbox label={t("assessments.settings.unlimited")} checked={d.unlimited} disabled={readOnly}
              onChange={(e) => setDefaults({ unlimited: e.target.checked })} />
          </div>
          <Select label={t("assessments.settings.scorePolicy")} value={d.scorePolicy} disabled={readOnly} error={err("defaults", "score_policy")}
            onChange={(e) => setDefaults({ scorePolicy: e.target.value as ScorePolicy })}
            options={SCORE_POLICIES.map((p) => ({ value: p, label: t(`assessments.scorePolicy.${p}`) }))} />
          <Select label={t("assessments.settings.resultsPolicy")} value={d.resultsPolicy} disabled={readOnly} error={err("defaults", "results_policy")}
            onChange={(e) => setDefaults({ resultsPolicy: e.target.value as ResultsPolicy })}
            options={RESULTS_POLICIES.map((p) => ({ value: p, label: t(`assessments.results.${p}`) }))} />
        </div>
        <div>
          <Checkbox label={t("assessments.settings.showCorrect")} checked={d.showCorrect} disabled={readOnly}
            onChange={(e) => setDefaults({ showCorrect: e.target.checked })} />
          <Checkbox label={t("assessments.settings.shuffleItems")} checked={d.shuffleItems} disabled={readOnly}
            onChange={(e) => setDefaults({ shuffleItems: e.target.checked })} />
          <Checkbox label={t("assessments.settings.shuffleChoices")} checked={d.shuffleChoices} disabled={readOnly}
            onChange={(e) => setDefaults({ shuffleChoices: e.target.checked })} />
        </div>
      </Card>

      <section aria-labelledby="spec-sections" className="space-y-3">
        <div>
          <h2 id="spec-sections" className="text-lg font-semibold text-slate-900">{t("examTemplates.specForm.sectionsCount", { n: draft.sections.length })}</h2>
          <p className="mt-1 text-sm text-slate-600">{t("examTemplates.specForm.sectionsHint")}</p>
          <FieldError>{err("sections")}</FieldError>
        </div>
        <ol className="space-y-3">
          {draft.sections.map((s, i) => (
            <li key={s.uid}>
              <SectionCard s={s} i={i} count={draft.sections.length} types={types} forward={forward} readOnly={readOnly}
                bound={bound.get(s.uid)} name={sectionName(i)} err={err}
                onChange={(patch) => setSection(s.uid, patch)} onMove={(by) => move(i, by)} onRemove={() => remove(s.uid)} />
            </li>
          ))}
        </ol>
        {!readOnly && (
          <Button variant="secondary" leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />} onClick={add}>
            {t("examTemplates.specForm.addSection")}
          </Button>
        )}
      </section>

      {showParams && (
        <Card className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{t("examTemplates.specForm.parameters")}</h2>
            <p className="mt-1 text-sm text-slate-600">{t("examTemplates.specForm.parametersHint")}</p>
            <FieldError>{err("parameters")}</FieldError>
          </div>
          {draft.parameters.map((p, j) => (
            <fieldset key={p.uid} className="space-y-3 rounded-xl border border-slate-200 p-3">
              <div className="flex items-center justify-between gap-2">
                <legend className="text-sm font-semibold text-slate-900">{t("examTemplates.specForm.paramN", { n: j + 1 })}</legend>
                {!readOnly && (
                  <IconButton aria-label={t("examTemplates.specForm.removeParameter", { n: j + 1 })} icon={<Trash2 className="h-4 w-4" aria-hidden="true" />}
                    onClick={() => update((x) => ({ ...x, parameters: x.parameters.filter((q) => q.uid !== p.uid) }))} />
                )}
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Input label={t("examTemplates.specForm.paramKey")} value={p.key} disabled={readOnly} maxLength={40}
                  error={err("parameters", j, "key")} onChange={(e) => setParam(p.uid, { key: e.target.value })} />
                <Input label={t("examTemplates.specForm.paramOptions")} value={p.options} disabled={readOnly}
                  hint={t("examTemplates.specForm.paramOptionsHint")} error={err("parameters", j, "options")}
                  onChange={(e) => setParam(p.uid, { options: e.target.value })} />
                <Select label={t("examTemplates.specForm.paramSection")} value={p.section} disabled={readOnly}
                  placeholder={t("examTemplates.specForm.paramChoose")} error={err("parameters", j, "binds")}
                  onChange={(e) => setParam(p.uid, { section: e.target.value })}
                  options={draft.sections.map((s, i) => ({ value: s.uid, label: sectionName(i) }))} />
              </div>
            </fieldset>
          ))}
          {!readOnly && (
            <Button variant="secondary" size="sm" leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}
              onClick={() => update((x) => ({ ...x, parameters: [...x.parameters, newParameter()] }))}>
              {t("examTemplates.specForm.addParameter")}
            </Button>
          )}
        </Card>
      )}

      <Card className="space-y-2">
        <fieldset>
          <legend className="text-lg font-semibold text-slate-900">{t("examTemplates.specForm.lockScope")}</legend>
          <p className="mt-1 text-sm text-slate-600">{t("examTemplates.specForm.lockScopeHint")}</p>
          <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 sm:gap-x-4">
            {LOCK_SCOPE_KEYS.map((k) => (
              <Checkbox key={k} label={t(`examTemplates.specForm.lockKeys.${k}`)} checked={draft.lockScope.includes(k)} disabled={readOnly}
                onChange={() => toggleLock(k)} />
            ))}
          </div>
          <FieldError>{err("lock_scope")}</FieldError>
        </fieldset>
      </Card>

      {platform && !readOnly && <JsonDisclosure draft={draft} update={update} />}
    </>
  );
}

function SectionCard({ s, i, count, types, forward, readOnly, bound, name, err, onChange, onMove, onRemove }: {
  s: SectionDraft;
  i: number;
  count: number;
  types: string[];
  forward: boolean;
  readOnly: boolean;
  bound?: ParameterDraft;
  name: string;
  err: (...prefix: (string | number)[]) => string | undefined;
  onChange: (patch: Partial<SectionDraft>) => void;
  onMove: (by: number) => void;
  onRemove: () => void;
}) {
  const { lang, t } = useTranslation();
  const toggleType = (q: string) => onChange({ types: s.types.includes(q) ? s.types.filter((x) => x !== q) : [...s.types, q] });
  const key = sectionKey(s, !!bound) ?? "";
  const keyErr = err("sections", i, "key");
  return (
    <Card className="space-y-4">
      <div className="flex items-start justify-between gap-2">
        <h3 className="min-w-0 break-words pt-2.5 text-base font-semibold text-slate-900">
          {pickLocalized(s.title, lang as Lang) ? t("examTemplates.specForm.cardTitle", { n: i + 1, name }) : name}
        </h3>
        {!readOnly && (
          <div className="flex shrink-0 gap-1">
            <IconButton aria-label={t("examTemplates.specForm.moveUp", { n: i + 1 })} icon={<ArrowUp className="h-4 w-4" aria-hidden="true" />}
              disabled={i === 0} onClick={() => onMove(-1)} />
            <IconButton aria-label={t("examTemplates.specForm.moveDown", { n: i + 1 })} icon={<ArrowDown className="h-4 w-4" aria-hidden="true" />}
              disabled={i === count - 1} onClick={() => onMove(1)} />
            <IconButton aria-label={t("examTemplates.specForm.removeSection", { n: i + 1 })} icon={<Trash2 className="h-4 w-4" aria-hidden="true" />}
              variant="danger" disabled={count <= 1} onClick={onRemove} />
          </div>
        )}
      </div>
      <div>
        <LocalizedTextInput label={t("examTemplates.specForm.sectionTitle")} languages={LMS_LANGS} defaultLanguage={lang as Lang}
          value={s.title} onChange={(v) => onChange({ title: v })} maxLength={200} disabled={readOnly} />
        <FieldError>{err("sections", i, "title")}</FieldError>
      </div>
      <div>
        <LocalizedTextInput label={t("examTemplates.specForm.instructions")} languages={LMS_LANGS} defaultLanguage={lang as Lang}
          value={s.instructions} onChange={(v) => onChange({ instructions: v })} maxLength={5000} multiline disabled={readOnly} />
        <FieldError>{err("sections", i, "instructions")}</FieldError>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Input label={t("examTemplates.specForm.timeLimit")} inputMode="decimal" value={s.timeMin} disabled={readOnly || (!forward && !s.timeMin)}
          hint={forward ? t("examTemplates.specForm.timeLimitHint") : t("examTemplates.specForm.timeLimitFree")}
          error={err("sections", i, "time_limit_s")} onChange={(e) => onChange({ timeMin: e.target.value })} />
        <Input label={t("examTemplates.specForm.minItems")} inputMode="numeric" value={s.minItems} disabled={readOnly}
          hint={t("examTemplates.specForm.countsHint")} error={err("sections", i, "min_items")} onChange={(e) => onChange({ minItems: e.target.value })} />
        <Input label={t("examTemplates.specForm.maxItems")} inputMode="numeric" value={s.maxItems} disabled={readOnly}
          hint={t("examTemplates.specForm.countsHint")} error={err("sections", i, "max_items")} onChange={(e) => onChange({ maxItems: e.target.value })} />
      </div>
      <fieldset>
        <legend className="text-sm font-medium leading-6 text-slate-800">{t("examTemplates.specForm.types")}</legend>
        <div className="grid grid-cols-1 sm:grid-cols-2 sm:gap-x-4 lg:grid-cols-3">
          {types.map((q) => (
            <Checkbox key={q} label={t(questionTypeTitleKey(q))} checked={s.types.includes(q)} disabled={readOnly} onChange={() => toggleType(q)} />
          ))}
        </div>
        <FieldError>{err("sections", i, "allowed_types")}</FieldError>
        {!err("sections", i, "allowed_types") && <p className="text-sm text-slate-600">{t("examTemplates.specForm.typesHint")}</p>}
      </fieldset>
      <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2 sm:items-end">
        <Checkbox label={t("examTemplates.specForm.allowPassages")} checked={s.allowPassages} disabled={readOnly}
          error={err("sections", i, "allow_passages")} onChange={(e) => onChange({ allowPassages: e.target.checked })} />
        <Select label={t("examTemplates.specForm.passageDisplay")} value={s.passageDisplay} disabled={readOnly || !s.allowPassages}
          error={err("sections", i, "passage_display")} onChange={(e) => onChange({ passageDisplay: e.target.value })}
          options={[{ value: "", label: t("examTemplates.specForm.passageInherit") }, ...PASSAGE_DISPLAYS.map((p) => ({ value: p, label: t(passageRenderers[p].titleKey) }))]} />
      </div>
      <details className="group rounded-xl border border-slate-200 px-3 py-2" open={!!keyErr || undefined}>
        <summary className="flex min-h-11 cursor-pointer items-center text-sm font-medium text-slate-800">
          {t("examTemplates.specForm.advanced")}
          <span className="ml-2 truncate font-normal text-slate-600">{key ? `· ${t("examTemplates.specForm.keyShort", { key })}` : ""}</span>
        </summary>
        <div className="space-y-1 pb-2 pt-1">
          {bound ? (
            <p className="text-sm text-slate-700">{t("examTemplates.specForm.keyBound", { key: bound.key || "—" })}</p>
          ) : (
            <>
              <Input label={t("examTemplates.specForm.key")} value={key} maxLength={40} disabled={readOnly || s.keyAuto} spellCheck={false}
                hint={t("examTemplates.specForm.keyHint")} error={keyErr} className="font-mono"
                onChange={(e) => onChange({ key: e.target.value })} />
              <Checkbox label={t("examTemplates.specForm.keyAuto")} checked={s.keyAuto} disabled={readOnly}
                onChange={(e) => onChange(e.target.checked
                  ? { keyAuto: true }
                  : { keyAuto: false, key: keyFromTitle(keySourceTitle(s.title)) || s.key })} />
            </>
          )}
          {bound && keyErr && <FieldError>{keyErr}</FieldError>}
        </div>
      </details>
    </Card>
  );
}

function JsonDisclosure({ draft, update }: { draft: SpecDraft; update: Update }) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const apply = () => {
    let parsed: unknown;
    try { parsed = JSON.parse(text); } catch { setError(t("examTemplates.editor.jsonInvalid")); return; }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed) || !Array.isArray((parsed as ExamTemplateSpec).sections)) {
      setError(t("examTemplates.editor.jsonInvalid"));
      return;
    }
    setError(null);
    update(() => draftOf(parsed as ExamTemplateSpec));
    toast.success(t("examTemplates.specForm.jsonApplied"));
  };
  return (
    <details className="rounded-2xl border border-slate-200 bg-white px-4 py-2"
      onToggle={(e) => { if ((e.target as HTMLDetailsElement).open) { setText(JSON.stringify(specOf(draft), null, 2)); setError(null); } }}>
      <summary className="flex min-h-11 cursor-pointer items-center text-sm font-semibold text-slate-800">{t("examTemplates.specForm.json")}</summary>
      <div className="space-y-3 pb-3">
        <Textarea label={t("examTemplates.specForm.jsonLabel")} value={text} rows={16} spellCheck={false} className="font-mono text-sm"
          hint={t("examTemplates.specForm.jsonHint")} error={error ?? undefined} onChange={(e) => { setText(e.target.value); setError(null); }} />
        <Button variant="secondary" onClick={apply}>{t("examTemplates.specForm.jsonApply")}</Button>
      </div>
    </details>
  );
}
