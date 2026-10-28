"use client";

// Phase 8b S4: the sections editor of the Structure tab (PHASE_8B_DESIGN 9.1). Ordered cards: a collapsed row with
// number, title and chips; expanded: title, instructions, key, time limit, counts, allowed types (from the blocks
// catalog), passages. Move up/down buttons are always there (the only way on a phone); desktop also drags.
import React from "react";
import { AlertCircle, ArrowDown, ArrowUp, ChevronDown, GripVertical, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { BlocksOut } from "@/lib/lms/examTemplateTypes";
import { NEW_SECTION_EXCLUDED_TYPES } from "@/lib/lms/examTemplates";
import { questionTypeTitleKey } from "@/lib/lms/blocks";
import { pickLocalized } from "@/lib/lms/localized";
import { LMS_LANGS } from "@/lib/lms/types";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { useDragReorder } from "@/components/lms/assessments/useDragReorder";
import { Badge, Button, Checkbox, FieldError, IconButton, Input, Select, cn } from "@/components/ui";
import {
  boundSections, keyFromTitle, keySourceTitle, newSection, sectionKey, type ParameterDraft, type SectionDraft, type SpecDraft,
} from "./specDraft";
import { fieldId, type FieldErr, type Update } from "./parts";

export function passageDisplayLabel(t: (k: string) => string, key: string): string {
  return t(`examTemplates.blocks.passageDisplays.${key}`);
}

export function SectionList({ draft, update, readOnly, err, blocks, forward, sectionName, expanded, setExpanded }: {
  draft: SpecDraft;
  update: Update;
  readOnly: boolean;
  err: FieldErr;
  blocks: BlocksOut;
  forward: boolean;
  sectionName: (i: number) => string;
  expanded: Set<string>;
  setExpanded: (fn: (s: Set<string>) => Set<string>) => void;
}) {
  const { t } = useTranslation();
  const bound = boundSections(draft);
  const types = blocks.question_types.map((q) => q.key);

  const move = (from: number, to: number) => update((d) => {
    if (to < 0 || to >= d.sections.length || from === to) return d;
    const next = [...d.sections];
    const [s] = next.splice(from, 1);
    next.splice(to, 0, s);
    return { ...d, sections: next };
  });
  const drag = useDragReorder(move, !readOnly);
  const setSection = (uid: string, patch: Partial<SectionDraft>) =>
    update((d) => ({ ...d, sections: d.sections.map((s) => (s.uid === uid ? { ...s, ...patch } : s)) }));
  // a removed section takes the parameter that supplied its key with it
  const remove = (uid: string) => update((d) => ({
    ...d, sections: d.sections.filter((s) => s.uid !== uid), parameters: d.parameters.filter((p) => p.section !== uid),
  }));
  const add = () => {
    const s = newSection(types.filter((x) => !(NEW_SECTION_EXCLUDED_TYPES as readonly string[]).includes(x)));
    update((d) => ({ ...d, sections: [...d.sections, s] }));
    setExpanded((x) => new Set(x).add(s.uid));
    requestAnimationFrame(() => document.getElementById(fieldId("sections", draft.sections.length))?.scrollIntoView({ block: "nearest" }));
  };
  const toggle = (uid: string) => setExpanded((x) => {
    const n = new Set(x);
    if (n.has(uid)) n.delete(uid); else n.add(uid);
    return n;
  });

  return (
    <section aria-labelledby="tpl-sections" id={fieldId("sections")} className="space-y-3">
      <div>
        <h2 id="tpl-sections" className="text-lg font-semibold text-slate-900">{t("examTemplates.specForm.sectionsCount", { n: draft.sections.length })}</h2>
        <p className="mt-1 text-sm text-slate-600">{t("examTemplates.specForm.sectionsHint")}</p>
        <FieldError>{err("sections")}</FieldError>
      </div>
      <ol className="space-y-3">
        {draft.sections.map((s, i) => {
          const open = expanded.has(s.uid);
          return (
            <li key={s.uid} id={fieldId("sections", i)} {...(open ? {} : drag(i))}>
              <SectionCard s={s} i={i} count={draft.sections.length} types={types} forward={forward} readOnly={readOnly} open={open}
                bound={bound.get(s.uid)} name={sectionName(i)} err={err} blocks={blocks}
                onToggle={() => toggle(s.uid)} onChange={(patch) => setSection(s.uid, patch)}
                onMove={(by) => move(i, i + by)} onRemove={() => remove(s.uid)} />
            </li>
          );
        })}
      </ol>
      {!readOnly && (
        <Button variant="secondary" leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />} onClick={add}>
          {t("examTemplates.specForm.addSection")}
        </Button>
      )}
    </section>
  );
}

function SectionCard({ s, i, count, types, forward, readOnly, open, bound, name, err, blocks, onToggle, onChange, onMove, onRemove }: {
  s: SectionDraft;
  i: number;
  count: number;
  types: string[];
  forward: boolean;
  readOnly: boolean;
  open: boolean;
  bound?: ParameterDraft;
  name: string;
  err: FieldErr;
  blocks: BlocksOut;
  onToggle: () => void;
  onChange: (patch: Partial<SectionDraft>) => void;
  onMove: (by: number) => void;
  onRemove: () => void;
}) {
  const { lang, t } = useTranslation();
  const toggleType = (q: string) => onChange({ types: s.types.includes(q) ? s.types.filter((x) => x !== q) : [...s.types, q] });
  const key = sectionKey(s, !!bound) ?? "";
  const keyErr = err("sections", i, "key");
  const hasIssue = !!err("sections", i);
  const titled = !!pickLocalized(s.title, lang);
  const bodyId = `${fieldId("sections", i)}-body`;
  const min = s.minItems.trim();
  const max = s.maxItems.trim();
  const counts = min && max ? t("examTemplates.counts.range", { min, max }) : min ? t("examTemplates.counts.min", { min }) : max ? t("examTemplates.counts.max", { max }) : "";

  return (
    <div className={cn("rounded-2xl border bg-white shadow-sm", hasIssue ? "border-danger-300" : "border-slate-200")}>
      <div className="flex items-start gap-1 p-2 sm:p-3">
        {!readOnly && !open && (
          <span aria-hidden="true" className="hidden min-h-11 cursor-grab items-center px-1 text-slate-400 sm:flex">
            <GripVertical className="h-4 w-4" />
          </span>
        )}
        <button type="button" onClick={onToggle} aria-expanded={open} aria-controls={bodyId}
          className="flex min-h-11 min-w-0 flex-1 items-start gap-2 rounded-xl px-2 py-1.5 text-left hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600">
          <span className="mt-0.5 inline-flex h-6 min-w-[1.5rem] shrink-0 items-center justify-center rounded-full bg-slate-100 px-1.5 text-xs font-semibold text-slate-700">{i + 1}</span>
          <span className="min-w-0 flex-1">
            <span className={cn("block break-words font-semibold", titled ? "text-slate-900" : "italic text-slate-600")}>
              {titled ? name : t("examTemplates.constructor.section.untitled")}
            </span>
            <span className="mt-1 flex flex-wrap gap-1.5">
              <Badge tone="neutral">{t("examTemplates.constructor.section.typesChip", { n: s.types.length })}</Badge>
              {s.allowPassages && <Badge tone="neutral">{t("examTemplates.constructor.section.passagesChip")}</Badge>}
              {counts && <Badge tone="neutral">{counts}</Badge>}
              {s.timeMin.trim() && <Badge tone="neutral">{t("examTemplates.picker.minutes", { n: s.timeMin.trim() })}</Badge>}
              {bound && <Badge tone="info">{t("examTemplates.constructor.section.boundChip", { key: bound.key || "—" })}</Badge>}
              {hasIssue && <Badge tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />}>{t("examTemplates.constructor.section.hasIssues")}</Badge>}
            </span>
          </span>
          <ChevronDown aria-hidden="true" className={cn("mt-1 h-5 w-5 shrink-0 text-slate-500 transition-transform", open && "rotate-180")} />
        </button>
        {!readOnly && (
          <div className="flex shrink-0 flex-col gap-1 sm:flex-row">
            <IconButton aria-label={t("examTemplates.specForm.moveUp", { n: i + 1 })} icon={<ArrowUp className="h-4 w-4" aria-hidden="true" />}
              disabled={i === 0} onClick={() => onMove(-1)} />
            <IconButton aria-label={t("examTemplates.specForm.moveDown", { n: i + 1 })} icon={<ArrowDown className="h-4 w-4" aria-hidden="true" />}
              disabled={i === count - 1} onClick={() => onMove(1)} />
          </div>
        )}
      </div>

      {open && (
        <div id={bodyId} className="space-y-4 border-t border-slate-200 p-4 sm:p-5">
          <div id={fieldId("sections", i, "title")}>
            <LocalizedTextInput label={t("examTemplates.specForm.sectionTitle")} languages={LMS_LANGS} defaultLanguage={lang}
              value={s.title} onChange={(v) => onChange({ title: v })} maxLength={200} disabled={readOnly} />
            <FieldError>{err("sections", i, "title")}</FieldError>
          </div>
          <div id={fieldId("sections", i, "instructions")}>
            <LocalizedTextInput label={t("examTemplates.specForm.instructions")} languages={LMS_LANGS} defaultLanguage={lang}
              value={s.instructions} onChange={(v) => onChange({ instructions: v })} maxLength={5000} multiline disabled={readOnly} />
            <FieldError>{err("sections", i, "instructions")}</FieldError>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {(forward || s.timeMin.trim() !== "" || !!err("sections", i, "time_limit_s")) ? (
              <Input id={fieldId("sections", i, "time_limit_s")} label={t("examTemplates.specForm.timeLimit")} inputMode="decimal" value={s.timeMin}
                disabled={readOnly} hint={forward ? t("examTemplates.specForm.timeLimitHint") : t("examTemplates.specForm.timeLimitFree")}
                error={err("sections", i, "time_limit_s")} onChange={(e) => onChange({ timeMin: e.target.value })} />
            ) : (
              <p className="text-sm text-slate-600 sm:pt-7">{t("examTemplates.constructor.section.timerNeedsForward")}</p>
            )}
            <Input id={fieldId("sections", i, "min_items")} label={t("examTemplates.specForm.minItems")} inputMode="numeric" value={s.minItems}
              disabled={readOnly} hint={t("examTemplates.specForm.countsHint")} error={err("sections", i, "min_items")}
              onChange={(e) => onChange({ minItems: e.target.value })} />
            <Input id={fieldId("sections", i, "max_items")} label={t("examTemplates.specForm.maxItems")} inputMode="numeric" value={s.maxItems}
              disabled={readOnly} hint={t("examTemplates.specForm.countsHint")} error={err("sections", i, "max_items")}
              onChange={(e) => onChange({ maxItems: e.target.value })} />
          </div>
          <fieldset id={fieldId("sections", i, "allowed_types")}>
            <legend className="text-sm font-medium leading-6 text-slate-800">{t("examTemplates.specForm.types")}</legend>
            <div className="grid grid-cols-1 sm:grid-cols-2 sm:gap-x-4 lg:grid-cols-3">
              {types.map((q) => (
                <Checkbox key={q} label={t(blocks.question_types.find((x) => x.key === q)?.title_key ?? questionTypeTitleKey(q))}
                  checked={s.types.includes(q)} disabled={readOnly} onChange={() => toggleType(q)} />
              ))}
            </div>
            <FieldError>{err("sections", i, "allowed_types")}</FieldError>
            {!err("sections", i, "allowed_types") && <p className="text-sm text-slate-600">{t("examTemplates.specForm.typesHint")}</p>}
          </fieldset>
          <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2 sm:items-end">
            <Checkbox id={fieldId("sections", i, "allow_passages")} label={t("examTemplates.specForm.allowPassages")} checked={s.allowPassages}
              disabled={readOnly} error={err("sections", i, "allow_passages")} onChange={(e) => onChange({ allowPassages: e.target.checked })} />
            <Select id={fieldId("sections", i, "passage_display")} label={t("examTemplates.specForm.passageDisplay")} value={s.passageDisplay}
              disabled={readOnly || !s.allowPassages} error={err("sections", i, "passage_display")}
              onChange={(e) => onChange({ passageDisplay: e.target.value })}
              options={[{ value: "", label: t("examTemplates.specForm.passageInherit") }, ...blocks.passage_displays.map((p) => ({ value: p, label: passageDisplayLabel(t, p) }))]} />
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
                  <Input id={fieldId("sections", i, "key")} label={t("examTemplates.specForm.key")} value={key} maxLength={40}
                    disabled={readOnly || s.keyAuto} spellCheck={false} hint={t("examTemplates.specForm.keyHint")} error={keyErr} className="font-mono"
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
          {!readOnly && (
            <div className="flex justify-end border-t border-slate-200 pt-3">
              <Button variant="dangerOutline" size="sm" leftIcon={<Trash2 className="h-4 w-4" aria-hidden="true" />} disabled={count <= 1}
                aria-label={t("examTemplates.specForm.removeSection", { n: i + 1 })} onClick={onRemove}>
                {t("examTemplates.constructor.section.remove")}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
