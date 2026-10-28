"use client";

// Phase 8b S4: Structure tab (PHASE_8B_DESIGN 9.1): name and description, navigation, sections, parameters,
// defaults for new exams, and the raw JSON disclosure for the platform admin only.
import React, { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { BlocksOut, ExamTemplateSpec } from "@/lib/lms/examTemplateTypes";
import { FORWARD_ONLY_NAVIGATION } from "@/lib/lms/examTemplates";
import { RESULTS_POLICIES, SCORE_POLICIES, type Navigation, type ResultsPolicy, type ScorePolicy } from "@/lib/lms/assessmentTypes";
import { LMS_LANGS } from "@/lib/lms/types";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { Button, Card, Checkbox, FieldError, IconButton, Input, Select, Textarea, toast } from "@/components/ui";
import { draftOf, newParameter, specOf, type DefaultsDraft, type ParameterDraft, type SpecDraft } from "./specDraft";
import { RadioCards, fieldId, filledLang, type FieldErr, type Update } from "./parts";
import { SectionList } from "./SectionList";
import type { Meta } from "./useConstructor";

export const MAX_PARAMETERS = 5;

export function StructureTab({ draft, update, meta, setMeta, readOnly, err, blocks, platform, sectionName, expanded, setExpanded }: {
  draft: SpecDraft;
  update: Update;
  meta: Meta;
  setMeta: (patch: Partial<Meta>) => void;
  readOnly: boolean;
  err: FieldErr;
  blocks: BlocksOut;
  platform: boolean;
  sectionName: (i: number) => string;
  expanded: Set<string>;
  setExpanded: (fn: (s: Set<string>) => Set<string>) => void;
}) {
  const { lang, t } = useTranslation();
  const forward = draft.navigation === FORWARD_ONLY_NAVIGATION;
  return (
    <div className="space-y-6">
      <Card title={t("examTemplates.editor.general")}>
        <div className="space-y-4">
          <div id={fieldId("title")}>
            <LocalizedTextInput label={t("examTemplates.fields.title")} languages={LMS_LANGS} defaultLanguage={filledLang(meta.title, lang)} value={meta.title}
              onChange={(v) => setMeta({ title: v })} maxLength={200} required disabled={readOnly} />
            <FieldError>{err("title")}</FieldError>
          </div>
          <LocalizedTextInput label={t("examTemplates.fields.description")} languages={LMS_LANGS} defaultLanguage={filledLang(meta.description, filledLang(meta.title, lang))} value={meta.description}
            onChange={(v) => setMeta({ description: v })} maxLength={2000} multiline disabled={readOnly} />
        </div>
      </Card>

      <NavigationCard draft={draft} update={update} readOnly={readOnly} err={err} blocks={blocks} forward={forward} />

      <SectionList draft={draft} update={update} readOnly={readOnly} err={err} blocks={blocks} forward={forward}
        sectionName={sectionName} expanded={expanded} setExpanded={setExpanded} />

      <ParametersCard draft={draft} update={update} readOnly={readOnly} err={err} sectionName={sectionName} />

      <DefaultsCard draft={draft} update={update} readOnly={readOnly} err={err} />

      {platform && !readOnly && <JsonDisclosure draft={draft} update={update} />}
    </div>
  );
}

function NavigationCard({ draft, update, readOnly, err, blocks, forward }: {
  draft: SpecDraft;
  update: Update;
  readOnly: boolean;
  err: FieldErr;
  blocks: BlocksOut;
  forward: boolean;
}) {
  const { t } = useTranslation();
  return (
    <Card title={t("examTemplates.editor.navigation")}>
      <RadioCards id={fieldId("navigation")} legend={t("examTemplates.constructor.navigation.legend")} value={draft.navigation}
        disabled={readOnly} error={err("navigation")} columns={2}
        onChange={(v) => update((d) => ({ ...d, navigation: v as Navigation }))}
        options={blocks.navigations.map((n) => ({
          value: n, label: t(`assessments.navigation.${n}`), description: t(`examTemplates.constructor.navigation.body.${n}`),
        }))} />
      {forward && <p role="note" className="mt-3 text-sm text-slate-700">{t("examTemplates.constructor.navigation.timersHint")}</p>}
    </Card>
  );
}

function ParametersCard({ draft, update, readOnly, err, sectionName }: {
  draft: SpecDraft;
  update: Update;
  readOnly: boolean;
  err: FieldErr;
  sectionName: (i: number) => string;
}) {
  const { t } = useTranslation();
  const setParam = (uid: string, patch: Partial<ParameterDraft>) =>
    update((x) => ({ ...x, parameters: x.parameters.map((p) => (p.uid === uid ? { ...p, ...patch } : p)) }));
  return (
    <Card id={fieldId("parameters")} title={t("examTemplates.specForm.parameters")} description={t("examTemplates.specForm.parametersHint")}>
      <div className="space-y-4">
        <FieldError>{err("parameters")}</FieldError>
        {draft.parameters.length === 0 && <p className="text-sm text-slate-600">{t("examTemplates.constructor.parameters.empty")}</p>}
        {draft.parameters.map((p, j) => (
          <fieldset key={p.uid} id={fieldId("parameters", j)} className="space-y-3 rounded-xl border border-slate-200 p-3">
            <div className="flex items-center justify-between gap-2">
              <legend className="text-sm font-semibold text-slate-900">{t("examTemplates.specForm.paramN", { n: j + 1 })}</legend>
              {!readOnly && (
                <IconButton aria-label={t("examTemplates.specForm.removeParameter", { n: j + 1 })} icon={<Trash2 className="h-4 w-4" aria-hidden="true" />}
                  variant="danger" onClick={() => update((x) => ({ ...x, parameters: x.parameters.filter((q) => q.uid !== p.uid) }))} />
              )}
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <Input id={fieldId("parameters", j, "key")} label={t("examTemplates.specForm.paramKey")} value={p.key} disabled={readOnly} maxLength={40}
                spellCheck={false} className="font-mono" error={err("parameters", j, "key")} onChange={(e) => setParam(p.uid, { key: e.target.value })} />
              <Textarea id={fieldId("parameters", j, "options")} label={t("examTemplates.specForm.paramOptions")} value={p.options} rows={3}
                disabled={readOnly} spellCheck={false} className="font-mono" hint={t("examTemplates.constructor.parameters.optionsHint")}
                error={err("parameters", j, "options")} onChange={(e) => setParam(p.uid, { options: e.target.value })} />
              <Select id={fieldId("parameters", j, "binds")} label={t("examTemplates.specForm.paramSection")} value={p.section} disabled={readOnly}
                placeholder={t("examTemplates.specForm.paramChoose")} error={err("parameters", j, "binds")}
                onChange={(e) => setParam(p.uid, { section: e.target.value })}
                options={draft.sections.map((s, i) => ({ value: s.uid, label: sectionName(i) }))} />
            </div>
          </fieldset>
        ))}
        {!readOnly && (
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="secondary" size="sm" leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />} disabled={draft.parameters.length >= MAX_PARAMETERS}
              onClick={() => update((x) => ({ ...x, parameters: [...x.parameters, newParameter()] }))}>
              {t("examTemplates.specForm.addParameter")}
            </Button>
            {draft.parameters.length >= MAX_PARAMETERS && <p className="text-sm text-slate-600">{t("examTemplates.constructor.parameters.max", { n: MAX_PARAMETERS })}</p>}
          </div>
        )}
      </div>
    </Card>
  );
}

function DefaultsCard({ draft, update, readOnly, err }: { draft: SpecDraft; update: Update; readOnly: boolean; err: FieldErr }) {
  const { t } = useTranslation();
  const d = draft.defaults;
  const setDefaults = (patch: Partial<DefaultsDraft>) => update((x) => ({ ...x, defaults: { ...x.defaults, ...patch } }));
  return (
    <Card id={fieldId("defaults")} title={t("examTemplates.specForm.defaults")} description={t("examTemplates.specForm.defaultsHint")}>
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input id={fieldId("defaults", "time_limit_s")} label={t("examTemplates.specForm.totalTime")} inputMode="decimal" value={d.timeMin} disabled={readOnly}
            hint={t("examTemplates.specForm.totalTimeHint")} error={err("defaults", "time_limit_s")}
            onChange={(e) => setDefaults({ timeMin: e.target.value })} />
          <div>
            <Input id={fieldId("defaults", "allowed_attempts")} label={t("assessments.settings.attempts")} inputMode="numeric" value={d.attempts}
              disabled={readOnly || d.unlimited} error={err("defaults", "allowed_attempts")} onChange={(e) => setDefaults({ attempts: e.target.value })} />
            <Checkbox label={t("assessments.settings.unlimited")} checked={d.unlimited} disabled={readOnly}
              onChange={(e) => setDefaults({ unlimited: e.target.checked })} />
          </div>
          <Select id={fieldId("defaults", "score_policy")} label={t("assessments.settings.scorePolicy")} value={d.scorePolicy} disabled={readOnly}
            error={err("defaults", "score_policy")} onChange={(e) => setDefaults({ scorePolicy: e.target.value as ScorePolicy })}
            options={SCORE_POLICIES.map((p) => ({ value: p, label: t(`assessments.scorePolicy.${p}`) }))} />
          <Select id={fieldId("defaults", "results_policy")} label={t("assessments.settings.resultsPolicy")} value={d.resultsPolicy} disabled={readOnly}
            error={err("defaults", "results_policy")} onChange={(e) => setDefaults({ resultsPolicy: e.target.value as ResultsPolicy })}
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
      </div>
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
    toast.success(t("examTemplates.constructor.jsonApplied"));
  };
  return (
    <details className="rounded-2xl border border-slate-200 bg-white px-4 py-2"
      onToggle={(e) => { if ((e.target as HTMLDetailsElement).open) { setText(JSON.stringify(specOf(draft), null, 2)); setError(null); } }}>
      <summary className="flex min-h-11 cursor-pointer items-center text-sm font-semibold text-slate-800">{t("examTemplates.specForm.json")}</summary>
      <div className="space-y-3 pb-3">
        <Textarea label={t("examTemplates.specForm.jsonLabel")} value={text} rows={16} spellCheck={false} className="font-mono text-sm"
          hint={t("examTemplates.constructor.jsonHint")} error={error ?? undefined} onChange={(e) => { setText(e.target.value); setError(null); }} />
        <Button variant="secondary" onClick={apply}>{t("examTemplates.specForm.jsonApply")}</Button>
      </div>
    </details>
  );
}
