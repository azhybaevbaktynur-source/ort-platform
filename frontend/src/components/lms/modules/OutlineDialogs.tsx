"use client";

// Phase 8a S4a (PHASE_8A_DESIGN 8.1): the outline editor's dialogs: module settings (create and edit), prerequisites
// (earlier modules only; later ones disabled with a hint), completion requirement (types allowed by the item kind),
// item edit (title shown in the module, indent, web address) and move to another module.
import React, { useId, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { cleanLocalized, pickLocalized } from "@/lib/lms/localized";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import {
  THRESHOLD_REQUIREMENTS, requirementTypesFor, type CompletionMode, type ItemKind, type ItemStaffOut, type ModuleStaffOut,
  type RequirementIn, type RequirementType,
} from "@/lib/lms/modulesTypes";
import { Button, Checkbox, Dialog, Input, Select, Switch } from "@/components/ui";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { fromLocalInput, toLocalInput } from "@/components/lms/assessments/format";
import { fmtThreshold } from "./moduleUi";

export interface CourseLangs {
  languages: Lang[];
  defaultLanguage: Lang;
}

function ErrorLine({ text }: { text: string | null }) {
  if (!text) return null;
  return <p role="alert" className="rounded-xl border border-danger-200 bg-danger-50 px-3 py-2 text-sm text-danger-800">{text}</p>;
}

function RadioRow({ name, checked, onChange, label, hint, disabled }: {
  name: string; checked: boolean; onChange: () => void; label: React.ReactNode; hint?: React.ReactNode; disabled?: boolean;
}) {
  return (
    <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-xl px-1 py-2.5">
      <input type="radio" name={name} className="mt-1 h-4 w-4 shrink-0 accent-brand-600" checked={checked} disabled={disabled} onChange={onChange} />
      <span className="min-w-0">
        <span className="block text-base leading-6 text-slate-900 sm:text-sm">{label}</span>
        {hint && <span className="block text-sm leading-6 text-slate-600">{hint}</span>}
      </span>
    </label>
  );
}

// ---------------------------------------------------------------- module settings

export interface ModuleSettingsValue {
  title: LocalizedText;
  unlock_at: string | null;
  sequential: boolean;
  completion_mode: CompletionMode;
  published: boolean;
}

export function ModuleSettingsDialog({ open, module, langs, busy, error, onSave, onClose }: {
  open: boolean;
  /** null: create a new module */
  module: ModuleStaffOut | null;
  langs: CourseLangs;
  busy: boolean;
  error: string | null;
  onSave: (v: ModuleSettingsValue) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const formId = useId();
  const [title, setTitle] = useState<LocalizedText>(module?.title ?? {});
  const [unlock, setUnlock] = useState(toLocalInput(module?.unlock_at));
  const [sequential, setSequential] = useState(module?.sequential ?? false);
  const [mode, setMode] = useState<CompletionMode>(module?.completion_mode ?? "all");
  const [published, setPublished] = useState(module?.published ?? false);
  const [touched, setTouched] = useState(false);
  const cleaned = cleanLocalized(title, langs.languages);
  const titleOk = Object.keys(cleaned).length > 0;

  const submit = (ev: React.FormEvent) => {
    ev.preventDefault();
    setTouched(true);
    if (!titleOk) return;
    onSave({ title: cleaned, unlock_at: fromLocalInput(unlock), sequential, completion_mode: mode, published });
  };

  return (
    <Dialog open={open} onClose={onClose} busy={busy} size="lg"
      title={module ? t("modules.settings.editTitle") : t("modules.settings.createTitle")}
      footer={(
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t("lms.common.cancel")}</Button>
          <Button type="submit" form={formId} loading={busy}>{module ? t("lms.common.save") : t("modules.settings.create")}</Button>
        </>
      )}>
      <form id={formId} onSubmit={submit} noValidate className="space-y-5">
        <LocalizedTextInput label={t("modules.settings.titleLabel")} languages={langs.languages} defaultLanguage={langs.defaultLanguage}
          value={title} onChange={setTitle} maxLength={200} required disabled={busy} />
        {touched && !titleOk && <p role="alert" className="text-sm text-danger-700">{t("modules.settings.titleRequired")}</p>}
        <Input type="datetime-local" label={t("modules.settings.unlockAt")} hint={t("modules.settings.unlockAtHint")} optional
          value={unlock} disabled={busy} onChange={(e) => setUnlock(e.target.value)} />
        <Checkbox label={t("modules.settings.sequential")} hint={t("modules.settings.sequentialHint")} checked={sequential} disabled={busy}
          onChange={(e) => setSequential(e.target.checked)} />
        <fieldset>
          <legend className="text-sm font-medium leading-6 text-slate-800">{t("modules.settings.completionMode")}</legend>
          <RadioRow name={`${formId}-mode`} checked={mode === "all"} onChange={() => setMode("all")} label={t("modules.settings.modeAll")} disabled={busy} />
          <RadioRow name={`${formId}-mode`} checked={mode === "any"} onChange={() => setMode("any")} label={t("modules.settings.modeAny")} disabled={busy} />
        </fieldset>
        {!module && (
          <Switch label={t("modules.settings.publish")} hint={t("modules.settings.publishHint")} checked={published} disabled={busy} onChange={setPublished} />
        )}
        <ErrorLine text={error} />
      </form>
    </Dialog>
  );
}

// ---------------------------------------------------------------- prerequisites

export function PrerequisiteDialog({ open, module, modules, defaultLang, busy, error, onSave, onClose }: {
  open: boolean;
  module: ModuleStaffOut;
  modules: ModuleStaffOut[];
  defaultLang: Lang;
  busy: boolean;
  error: string | null;
  onSave: (ids: string[]) => void;
  onClose: () => void;
}) {
  const { lang, t } = useTranslation();
  const [picked, setPicked] = useState<string[]>(module.prerequisites);
  const others = modules.filter((m) => m.id !== module.id && !m.deleted_at);
  const earlier = others.filter((m) => m.position < module.position);
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const name = (m: ModuleStaffOut) => pickLocalized(m.title, lang, defaultLang) || t("modules.untitledModule");
  return (
    <Dialog open={open} onClose={onClose} busy={busy} size="md" title={t("modules.prereq.title")} description={name(module)}
      footer={(
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t("lms.common.cancel")}</Button>
          <Button onClick={() => onSave(picked.filter((id) => earlier.some((m) => m.id === id)))} loading={busy} disabled={earlier.length === 0}>{t("lms.common.save")}</Button>
        </>
      )}>
      <div className="space-y-3">
        <p className="text-sm leading-6 text-slate-700">{t("modules.prereq.hint")}</p>
        {earlier.length === 0 && <p className="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700">{t("modules.prereq.none")}</p>}
        <div>
          {others.map((m) => {
            const later = m.position > module.position;
            return (
              <Checkbox key={m.id} label={name(m)} checked={!later && picked.includes(m.id)} disabled={busy || later}
                hint={later ? t("modules.prereq.laterHint") : !m.published ? t("modules.prereq.unpublishedHint") : undefined}
                onChange={() => toggle(m.id)} />
            );
          })}
        </div>
        <ErrorLine text={error} />
      </div>
    </Dialog>
  );
}

// ---------------------------------------------------------------- completion requirement

/** Requirement radios for an item kind; `value` null = no requirement. Threshold for min_score / min_percent. */
export function RequirementFields({ kind, value, onChange, disabled }: {
  kind: ItemKind;
  value: { type: RequirementType | null; threshold: string };
  onChange: (v: { type: RequirementType | null; threshold: string }) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const name = useId();
  const types = requirementTypesFor(kind);
  if (types.length === 0) return <p className="text-sm text-slate-600">{t("modules.reqPicker.headerNone")}</p>;
  const needs = value.type && THRESHOLD_REQUIREMENTS.includes(value.type);
  return (
    <fieldset className="space-y-1">
      <legend className="text-sm font-medium leading-6 text-slate-800">{t("modules.reqPicker.label")}</legend>
      <RadioRow name={name} checked={value.type === null} onChange={() => onChange({ ...value, type: null })} label={t("modules.reqPicker.none")} disabled={disabled} />
      {types.map((ty) => (
        <RadioRow key={ty} name={name} checked={value.type === ty} onChange={() => onChange({ ...value, type: ty })}
          label={t(`modules.reqPicker.types.${ty}`)} disabled={disabled} />
      ))}
      {needs && (
        <div className="pl-8 pt-1">
          <Input type="number" inputMode="decimal" min={0} max={value.type === "min_percent" ? 100 : undefined} step="0.01"
            label={value.type === "min_percent" ? t("modules.reqPicker.thresholdPercent") : t("modules.reqPicker.thresholdPoints")}
            value={value.threshold} disabled={disabled} onChange={(e) => onChange({ ...value, threshold: e.target.value })}
            containerClassName="max-w-[12rem]" />
        </div>
      )}
    </fieldset>
  );
}

/** Parses the fields into a body: undefined = invalid threshold, null = no requirement. */
export function requirementBody(v: { type: RequirementType | null; threshold: string }): RequirementIn | null | undefined {
  if (!v.type) return null;
  if (!THRESHOLD_REQUIREMENTS.includes(v.type)) return { type: v.type };
  const n = Number(v.threshold.replace(",", "."));
  if (!v.threshold.trim() || !Number.isFinite(n) || n < 0 || (v.type === "min_percent" && n > 100)) return undefined;
  return { type: v.type, threshold: Math.round(n * 100) / 100 };
}

export function RequirementDialog({ open, item, itemTitle, busy, error, onSave, onClose }: {
  open: boolean;
  item: ItemStaffOut;
  itemTitle: string;
  busy: boolean;
  error: string | null;
  onSave: (body: RequirementIn | null) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [value, setValue] = useState<{ type: RequirementType | null; threshold: string }>({
    type: item.requirement?.type ?? null, threshold: fmtThreshold(item.requirement?.threshold),
  });
  const [invalid, setInvalid] = useState(false);
  const save = () => {
    const body = requirementBody(value);
    if (body === undefined) { setInvalid(true); return; }
    onSave(body);
  };
  return (
    <Dialog open={open} onClose={onClose} busy={busy} size="md" title={t("modules.reqPicker.title")} description={itemTitle}
      footer={(
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t("lms.common.cancel")}</Button>
          <Button onClick={save} loading={busy}>{t("lms.common.save")}</Button>
        </>
      )}>
      <div className="space-y-3">
        <RequirementFields kind={item.kind} value={value} onChange={(v) => { setValue(v); setInvalid(false); }} disabled={busy} />
        {invalid && <p role="alert" className="text-sm text-danger-700">{t("modules.reqPicker.thresholdInvalid")}</p>}
        {!item.published && <p className="text-sm text-warning-800">{t("modules.reqPicker.hiddenNote")}</p>}
        <ErrorLine text={error} />
      </div>
    </Dialog>
  );
}

// ---------------------------------------------------------------- item edit

export const INDENTS = [0, 1, 2, 3] as const;

export function ItemEditDialog({ open, item, langs, busy, error, onSave, onClose }: {
  open: boolean;
  item: ItemStaffOut;
  langs: CourseLangs;
  busy: boolean;
  error: string | null;
  onSave: (v: { title_override: LocalizedText | null; indent: number; url?: string }) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const formId = useId();
  const [title, setTitle] = useState<LocalizedText>(item.title_override ?? {});
  const [indent, setIndent] = useState(item.indent);
  const [url, setUrl] = useState(item.url ?? "");
  const [touched, setTouched] = useState(false);
  const cleaned = cleanLocalized(title, langs.languages);
  const hasTitle = Object.keys(cleaned).length > 0;
  const urlOk = item.kind !== "url" || /^https?:\/\/\S+$/i.test(url.trim());
  const titleOk = item.kind !== "header" || hasTitle;
  const submit = (ev: React.FormEvent) => {
    ev.preventDefault();
    setTouched(true);
    if (!urlOk || !titleOk) return;
    onSave({ title_override: hasTitle ? cleaned : null, indent, ...(item.kind === "url" ? { url: url.trim() } : {}) });
  };
  return (
    <Dialog open={open} onClose={onClose} busy={busy} size="lg" title={t("modules.itemEdit.title")}
      footer={(
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t("lms.common.cancel")}</Button>
          <Button type="submit" form={formId} loading={busy}>{t("lms.common.save")}</Button>
        </>
      )}>
      <form id={formId} onSubmit={submit} noValidate className="space-y-5">
        {item.kind === "url" && (
          <Input type="url" inputMode="url" label={t("modules.add.url")} hint={t("modules.add.urlHint")} value={url} disabled={busy}
            onChange={(e) => setUrl(e.target.value)} error={touched && !urlOk ? t("modules.errors.url_invalid") : undefined} />
        )}
        <LocalizedTextInput label={item.kind === "header" ? t("modules.add.headerTitle") : t("modules.add.titleOverride")}
          languages={langs.languages} defaultLanguage={langs.defaultLanguage} value={title} onChange={setTitle} maxLength={200}
          required={item.kind === "header"} disabled={busy} />
        {item.kind !== "header" && <p className="-mt-3 text-sm text-slate-600">{t("modules.add.titleOverrideHint")}</p>}
        {touched && !titleOk && <p role="alert" className="text-sm text-danger-700">{t("modules.add.headerRequired")}</p>}
        <Select label={t("modules.add.indent")} value={String(indent)} disabled={busy} onChange={(e) => setIndent(Number(e.target.value))}
          options={INDENTS.map((n) => ({ value: String(n), label: t(`modules.add.indentLevels.${n}`) }))} containerClassName="max-w-xs" />
        <ErrorLine text={error} />
      </form>
    </Dialog>
  );
}

// ---------------------------------------------------------------- move to another module

export function MoveItemDialog({ open, item, itemTitle, modules, defaultLang, busy, error, onMove, onClose }: {
  open: boolean;
  item: ItemStaffOut;
  itemTitle: string;
  modules: ModuleStaffOut[];
  defaultLang: Lang;
  busy: boolean;
  error: string | null;
  onMove: (moduleId: string, position: number) => void;
  onClose: () => void;
}) {
  const { lang, t } = useTranslation();
  const targets = modules.filter((m) => m.id !== item.module_id && !m.deleted_at);
  const [to, setTo] = useState(targets[0]?.id ?? "");
  const target = targets.find((m) => m.id === to);
  return (
    <Dialog open={open} onClose={onClose} busy={busy} size="md" title={t("modules.move.title")} description={itemTitle}
      footer={(
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t("lms.common.cancel")}</Button>
          <Button onClick={() => target && onMove(target.id, target.items.length + 1)} loading={busy} disabled={!target}>{t("modules.move.submit")}</Button>
        </>
      )}>
      <div className="space-y-3">
        {targets.length === 0 ? (
          <p className="text-sm text-slate-700">{t("modules.move.noTargets")}</p>
        ) : (
          <>
            <Select label={t("modules.move.target")} value={to} disabled={busy} onChange={(e) => setTo(e.target.value)}
              options={targets.map((m) => ({ value: m.id, label: pickLocalized(m.title, lang, defaultLang) || t("modules.untitledModule") }))} />
            <p className="text-sm text-slate-600">{t("modules.move.hint")}</p>
          </>
        )}
        <ErrorLine text={error} />
      </div>
    </Dialog>
  );
}
