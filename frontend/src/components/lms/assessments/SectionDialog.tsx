"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { QUESTION_TYPES, type QuestionType } from "@/lib/lms/contentTypes";
import { templateLockedFields, type AssessmentStaffOut, type SectionIn, type SectionOut } from "@/lib/lms/assessmentTypes";
import { isAssessmentLocked, isPresetRuleLocked, useTemplateUi } from "@/lib/lms/templates";
import { cleanLocalized } from "@/lib/lms/localized";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { inputCls, labelCls } from "@/components/lms/content/ui";
import { btnPrimary, btnSecondary } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { AssessmentError } from "./AssessmentError";
import { Modal } from "./Modal";
import { minToSec, secToMin } from "./format";

/** Add or edit a section: key, titles, instructions, time limit and rules. */
export function SectionDialog({
  open, section, assessment, languages, defaultLanguage, busy, error, onSubmit, onCancel,
}: {
  open: boolean;
  section: SectionOut | null;
  assessment: AssessmentStaffOut;
  languages: Lang[];
  defaultLanguage: Lang;
  busy: boolean;
  error: unknown;
  onSubmit: (v: SectionIn) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [key, setKey] = useState("");
  const [title, setTitle] = useState<LocalizedText>({});
  const [instructions, setInstructions] = useState<LocalizedText>({});
  const [limit, setLimit] = useState("");
  const [types, setTypes] = useState<QuestionType[]>([]);
  const [passages, setPassages] = useState(false);
  useEffect(() => {
    if (!open) return;
    setKey(section?.key ?? "");
    setTitle(section?.title ?? {});
    setInstructions(section?.instructions ?? {});
    setLimit(secToMin(section?.time_limit_s));
    setTypes(section?.rules.allowed_types ?? []);
    setPassages(section?.rules.allow_passages ?? false);
  }, [open, section]);

  const ui = useTemplateUi();
  // Template lock (design §5.4): section key, time limit and rules are fixed; greyed out, never hidden.
  const tplLocked = isAssessmentLocked(ui, assessment.preset); // Phase 6 S4b: free (`none`) assessments are not locked
  // --- Phase 7b S5: fields fixed by a locked exam template (empty for blank and preset exams) ---
  const examLocks = templateLockedFields(assessment);
  const keyLocked = tplLocked || examLocks.has("section_key");
  const limitLocked = tplLocked || examLocks.has("section_time_limit_s");
  const rulesLocked = examLocks.has("section_rules");
  const examLocked = keyLocked !== tplLocked || limitLocked !== tplLocked || rulesLocked;
  // --- Phase 7b S5 end ---
  const locked = tplLocked || rulesLocked || isPresetRuleLocked(assessment.preset, section?.key);
  const free = assessment.navigation === "free";
  const toggleType = (q: QuestionType) => setTypes((c) => (c.includes(q) ? c.filter((x) => x !== q) : [...c, q]));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const rules = { ...(section?.rules ?? {}) };
    if (!locked) {
      if (types.length) rules.allowed_types = types; else delete rules.allowed_types;
    }
    if (!rulesLocked) rules.allow_passages = passages;
    // Phase 7b S5: fields fixed by an exam template are not sent (the server answers 409 template_locked on a change)
    onSubmit({
      ...(examLocks.has("section_key") ? {} : { key: key.trim() || null }),
      title: cleanLocalized(title, languages),
      instructions: cleanLocalized(instructions, languages),
      ...(examLocks.has("section_time_limit_s") ? {} : { time_limit_s: minToSec(limit) }),
      ...(rulesLocked ? {} : { rules }),
    });
  };

  return (
    <Modal open={open} title={section ? t("assessments.section.editTitle") : t("assessments.section.addTitle")} onClose={onCancel} busy={busy}>
      <form onSubmit={submit} className="space-y-4">
        {tplLocked && <p role="note" className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">{t("templates.lockedNote")}</p>}
        {!tplLocked && examLocked && <p role="note" className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{t("examTemplates.lockedSectionFields")}</p>}
        <div>
          <label className={labelCls} htmlFor="sec-key">{t("assessments.section.key")}</label>
          <input id="sec-key" list={ui.sectionKeys.length ? "sec-keys" : undefined} className={inputCls} maxLength={40} value={key} disabled={keyLocked} aria-describedby="sec-key-hint" onChange={(e) => setKey(e.target.value)} />
          <p id="sec-key-hint" className="mt-1 text-xs text-slate-500">{t("assessments.section.keyHint")}</p>{/* Phase 7b S7 */}
          {ui.sectionKeys.length > 0 && <datalist id="sec-keys">{ui.sectionKeys.map((k) => <option key={k} value={k}>{t(`sections.${k}`)}</option>)}</datalist>}
        </div>
        <LocalizedTextInput label={t("assessments.section.titleLabel")} languages={languages} defaultLanguage={defaultLanguage} value={title} onChange={setTitle} maxLength={200} />
        <LocalizedTextInput label={t("assessments.section.instructions")} languages={languages} defaultLanguage={defaultLanguage} value={instructions} onChange={setInstructions} multiline />
        <div>
          <label className={labelCls} htmlFor="sec-limit">{t("assessments.section.timeLimit")}</label>
          <input id="sec-limit" type="number" min={1} max={1440} className={inputCls} disabled={free || limitLocked} value={limit} onChange={(e) => setLimit(e.target.value)} />
          <p className="mt-1 text-xs text-slate-500">{free ? t("assessments.section.timeLimitFreeHint") : t("assessments.section.timeLimitHint")}</p>
        </div>
        <fieldset disabled={locked}>
          <legend className={labelCls}>{t("assessments.section.allowedTypes")}</legend>
          <div className="flex flex-wrap gap-2">
            {QUESTION_TYPES.map((q) => (
              <label key={q} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-2.5 py-1 text-xs">
                <input type="checkbox" checked={types.includes(q)} onChange={() => toggleType(q)} />{t(`bank.types.${q}.name`)}
              </label>
            ))}
          </div>
          <p className="mt-1 text-xs text-slate-500">{tplLocked ? t("templates.lockedNote") : rulesLocked ? t("examTemplates.lockedNote") : locked ? t("assessments.section.rulesLocked") : t("assessments.section.allowedTypesHint")}</p>
        </fieldset>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={passages} disabled={tplLocked || rulesLocked} onChange={(e) => setPassages(e.target.checked)} />{t("assessments.section.allowPassages")}
        </label>
        <AssessmentError error={error} />
        <div className="flex justify-end gap-2">
          <button type="button" className={btnSecondary} disabled={busy} onClick={onCancel}>{t("lms.common.cancel")}</button>
          <button type="submit" className={btnPrimary} disabled={busy || ((tplLocked || examLocks.has("section_add_remove")) && !section)}>{busy ? t("lms.common.loading") : t("lms.common.save")}</button>
        </div>
      </form>
    </Modal>
  );
}
