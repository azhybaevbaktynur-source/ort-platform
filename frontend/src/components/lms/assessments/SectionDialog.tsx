"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { QUESTION_TYPES, type QuestionType } from "@/lib/lms/contentTypes";
import type { AssessmentStaffOut, SectionIn, SectionOut } from "@/lib/lms/assessmentTypes";
import { ORT_SECTIONS } from "@/lib/lms/contentTypes";
import { cleanLocalized } from "@/lib/lms/localized";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { btnPrimary, btnSecondary, inputCls, labelCls } from "@/components/lms/content/ui";
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

  const locked = assessment.preset !== "none" && !!section?.key && ORT_SECTIONS.some((k) => k === section.key);
  const free = assessment.navigation === "free";
  const toggleType = (q: QuestionType) => setTypes((c) => (c.includes(q) ? c.filter((x) => x !== q) : [...c, q]));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const rules = { ...(section?.rules ?? {}) };
    if (!locked) {
      if (types.length) rules.allowed_types = types; else delete rules.allowed_types;
    }
    rules.allow_passages = passages;
    onSubmit({
      key: key.trim() || null,
      title: cleanLocalized(title, languages),
      instructions: cleanLocalized(instructions, languages),
      time_limit_s: minToSec(limit),
      rules,
    });
  };

  return (
    <Modal open={open} title={section ? t("assessments.section.editTitle") : t("assessments.section.addTitle")} onClose={onCancel} busy={busy}>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className={labelCls} htmlFor="sec-key">{t("assessments.section.key")}</label>
          <input id="sec-key" list="sec-keys" className={inputCls} maxLength={40} value={key} onChange={(e) => setKey(e.target.value)} />
          <datalist id="sec-keys">{ORT_SECTIONS.map((k) => <option key={k} value={k}>{t(`sections.${k}`)}</option>)}</datalist>
        </div>
        <LocalizedTextInput label={t("assessments.section.titleLabel")} languages={languages} defaultLanguage={defaultLanguage} value={title} onChange={setTitle} maxLength={200} />
        <LocalizedTextInput label={t("assessments.section.instructions")} languages={languages} defaultLanguage={defaultLanguage} value={instructions} onChange={setInstructions} multiline />
        <div>
          <label className={labelCls} htmlFor="sec-limit">{t("assessments.section.timeLimit")}</label>
          <input id="sec-limit" type="number" min={1} max={1440} className={inputCls} disabled={free} value={limit} onChange={(e) => setLimit(e.target.value)} />
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
          <p className="mt-1 text-xs text-slate-500">{locked ? t("assessments.section.rulesLocked") : t("assessments.section.allowedTypesHint")}</p>
        </fieldset>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={passages} onChange={(e) => setPassages(e.target.checked)} />{t("assessments.section.allowPassages")}
        </label>
        <AssessmentError error={error} />
        <div className="flex justify-end gap-2">
          <button type="button" className={btnSecondary} disabled={busy} onClick={onCancel}>{t("lms.common.cancel")}</button>
          <button type="submit" className={btnPrimary} disabled={busy}>{busy ? t("lms.common.loading") : t("lms.common.save")}</button>
        </div>
      </form>
    </Modal>
  );
}
