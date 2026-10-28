"use client";

// Phase 8b S4: Display tab (PHASE_8B_DESIGN 9.1): how questions are shown (display mode with small inline
// illustrations), how reading passages are shown (default + per-section overrides), and what a lock fixes.
import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { BlocksOut, LockScopeKey } from "@/lib/lms/examTemplateTypes";
import { DEFAULT_DISPLAY_MODE } from "@/lib/lms/examTemplates";
import { Card, Checkbox, FieldError, Select } from "@/components/ui";
import { RadioCards, fieldId, type FieldErr, type Update } from "./parts";
import { passageDisplayLabel } from "./SectionList";
import type { SpecDraft } from "./specDraft";

export function DisplayTab({ draft, update, readOnly, err, blocks, sectionName }: {
  draft: SpecDraft;
  update: Update;
  readOnly: boolean;
  err: FieldErr;
  blocks: BlocksOut;
  sectionName: (i: number) => string;
}) {
  const { t } = useTranslation();
  const passageOptions = blocks.passage_displays.map((p) => ({ value: p, label: passageDisplayLabel(t, p) }));
  const toggleLock = (k: LockScopeKey) =>
    update((d) => ({ ...d, lockScope: d.lockScope.includes(k) ? d.lockScope.filter((x) => x !== k) : [...d.lockScope, k] }));
  const withPassages = draft.sections.map((s, i) => ({ s, i })).filter(({ s }) => s.allowPassages);

  return (
    <div className="space-y-6">
      <Card title={t("examTemplates.editor.displayMode")}>
        <RadioCards id={fieldId("display_mode")} legend={t("examTemplates.constructor.displayMode.legend")} value={draft.displayMode}
          disabled={readOnly} error={err("display_mode")} onChange={(v) => update((d) => ({ ...d, displayMode: v }))}
          options={blocks.display_modes.map((m) => ({
            value: m, label: t(`examTemplates.blocks.displayModes.${m}`), description: t(`examTemplates.constructor.displayMode.body.${m}`),
            illustration: m === DEFAULT_DISPLAY_MODE ? <OnePerPageArt /> : <ScrollingArt />,
          }))} />
      </Card>

      <Card title={t("examTemplates.editor.passageDisplay")} description={t("examTemplates.constructor.passageDisplay.body")}>
        <div className="space-y-4">
          <Select id={fieldId("passage_display")} label={t("examTemplates.constructor.passageDisplay.default")} value={draft.passageDisplay}
            disabled={readOnly} error={err("passage_display")} containerClassName="sm:max-w-sm"
            onChange={(e) => update((d) => ({ ...d, passageDisplay: e.target.value }))}
            options={[{ value: "", label: t("examTemplates.editor.courseDefault") }, ...passageOptions]} />
          <div>
            <h3 className="text-sm font-medium leading-6 text-slate-800">{t("examTemplates.constructor.passageDisplay.perSection")}</h3>
            {withPassages.length === 0 ? (
              <p className="text-sm text-slate-600">{t("examTemplates.constructor.passageDisplay.none")}</p>
            ) : (
              <ul className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {withPassages.map(({ s, i }) => (
                  <li key={s.uid}>
                    <Select label={sectionName(i)} value={s.passageDisplay} disabled={readOnly} error={err("sections", i, "passage_display")}
                      onChange={(e) => update((d) => ({ ...d, sections: d.sections.map((x) => (x.uid === s.uid ? { ...x, passageDisplay: e.target.value } : x)) }))}
                      options={[{ value: "", label: t("examTemplates.specForm.passageInherit") }, ...passageOptions]} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Card>

      <Card id={fieldId("lock_scope")} title={t("examTemplates.specForm.lockScope")} description={t("examTemplates.specForm.lockScopeHint")}>
        <fieldset>
          <legend className="sr-only">{t("examTemplates.specForm.lockScope")}</legend>
          <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            {blocks.lock_scope_keys.map((k) => (
              <Checkbox key={k} label={t(`examTemplates.specForm.lockKeys.${k}`)} hint={t(`examTemplates.constructor.lockScope.${k}`)}
                checked={draft.lockScope.includes(k as LockScopeKey)} disabled={readOnly} onChange={() => toggleLock(k as LockScopeKey)} />
            ))}
          </div>
          <FieldError>{err("lock_scope")}</FieldError>
        </fieldset>
      </Card>
    </div>
  );
}

/** One question per page: a single question card with Back / Next. */
function OnePerPageArt() {
  return (
    <svg width="72" height="56" viewBox="0 0 72 56" className="text-slate-400">
      <rect x="1" y="1" width="70" height="54" rx="6" fill="white" stroke="currentColor" strokeWidth="1.5" />
      <rect x="9" y="9" width="40" height="5" rx="2.5" fill="currentColor" />
      <rect x="9" y="19" width="30" height="4" rx="2" className="text-slate-300" fill="currentColor" />
      <rect x="9" y="27" width="30" height="4" rx="2" className="text-slate-300" fill="currentColor" />
      <rect x="9" y="42" width="16" height="7" rx="3" className="text-slate-300" fill="currentColor" />
      <rect x="47" y="42" width="16" height="7" rx="3" className="text-brand-500" fill="currentColor" />
    </svg>
  );
}

/** All questions on one page: stacked question cards. */
function ScrollingArt() {
  return (
    <svg width="72" height="56" viewBox="0 0 72 56" className="text-slate-400">
      <rect x="1" y="1" width="70" height="54" rx="6" fill="white" stroke="currentColor" strokeWidth="1.5" />
      {[7, 22, 37].map((y) => (
        <g key={y}>
          <rect x="7" y={y} width="58" height="12" rx="3" fill="none" stroke="currentColor" strokeWidth="1.2" />
          <rect x="11" y={y + 4} width="26" height="4" rx="2" fill="currentColor" />
        </g>
      ))}
    </svg>
  );
}
