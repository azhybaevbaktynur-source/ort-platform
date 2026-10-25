"use client";

import React from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { ImagePicker } from "../ImagePicker";
import { RichTextField } from "../RichTextField";
import { inputCls, labelCls } from "../ui";
import { btnSmall } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { nextChoiceId, type ChoiceForm, type QuestionForm } from "./formModel";

/** single_choice and multiple_answers: choices with letters as ids, mark correct, reorder, optional images. */
export function ChoiceFields({
  courseId, form, onChange, disabled,
}: { courseId: string; form: QuestionForm; onChange: (patch: Partial<QuestionForm>) => void; disabled?: boolean }) {
  const { t } = useTranslation();
  const multi = form.type === "multiple_answers";
  const setChoices = (choices: ChoiceForm[]) => onChange({ choices });
  const update = (i: number, patch: Partial<ChoiceForm>) => setChoices(form.choices.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const move = (i: number, d: -1 | 1) => {
    const j = i + d;
    if (j < 0 || j >= form.choices.length) return;
    const next = [...form.choices];
    [next[i], next[j]] = [next[j], next[i]];
    setChoices(next);
  };
  const remove = (i: number) => {
    const removed = form.choices[i];
    onChange({
      choices: form.choices.filter((_, j) => j !== i),
      correctSingle: form.correctSingle === removed.id ? "" : form.correctSingle,
      correctMulti: form.correctMulti.filter((x) => x !== removed.id),
    });
  };
  const add = () => setChoices([...form.choices, { id: nextChoiceId(form.choices), text: "", image: null }]);
  const toggleMulti = (id: string) =>
    onChange({ correctMulti: form.correctMulti.includes(id) ? form.correctMulti.filter((x) => x !== id) : [...form.correctMulti, id] });

  return (
    <div className="space-y-3">
      <span className={labelCls}>{t("bank.editor.choices")}</span>
      <ul className="space-y-3">
        {form.choices.map((c, i) => {
          const checked = multi ? form.correctMulti.includes(c.id) : form.correctSingle === c.id;
          return (
            <li key={c.id} className={`rounded-xl border p-3 ${checked ? "border-emerald-300 bg-emerald-50/40" : "border-slate-200"}`}>
              <div className="mb-2 flex items-center gap-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 text-sm font-bold text-slate-700">{c.id}</span>
                <label className="flex items-center gap-1.5 text-sm text-slate-700">
                  <input type={multi ? "checkbox" : "radio"} name="correct-choice" disabled={disabled} checked={checked}
                    onChange={() => (multi ? toggleMulti(c.id) : onChange({ correctSingle: c.id }))} />
                  {t("bank.editor.correct")}
                </label>
                <span className="ml-auto flex gap-1">
                  <button type="button" disabled={disabled || i === 0} className={btnSmall} onClick={() => move(i, -1)} aria-label={t("bank.editor.moveUp")}>
                    <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <button type="button" disabled={disabled || i === form.choices.length - 1} className={btnSmall} onClick={() => move(i, 1)} aria-label={t("bank.editor.moveDown")}>
                    <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <button type="button" disabled={disabled || form.choices.length <= 2} className={btnSmall} onClick={() => remove(i)} aria-label={t("bank.editor.removeChoice")}>
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </span>
              </div>
              <RichTextField compact rows={2} value={c.text} disabled={disabled} onChange={(v) => update(i, { text: v })} />
              <div className="mt-2">
                <ImagePicker compact courseId={courseId} value={c.image} disabled={disabled} onChange={(img) => update(i, { image: img })} />
              </div>
            </li>
          );
        })}
      </ul>
      <button type="button" disabled={disabled || form.choices.length >= 10} className={btnSmall} onClick={add}>
        <Plus className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" />{t("bank.editor.addChoice")}
      </button>
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-1.5 text-sm text-slate-700">
          <input type="checkbox" disabled={disabled} checked={form.shuffle} onChange={(e) => onChange({ shuffle: e.target.checked })} />
          {t("bank.editor.shuffle")}
        </label>
        {multi && (
          <label className="flex items-center gap-2 text-sm text-slate-700">
            {t("bank.editor.scoring")}
            <select disabled={disabled} className={`${inputCls} w-auto`} value={form.scoring}
              onChange={(e) => onChange({ scoring: e.target.value as QuestionForm["scoring"] })}>
              <option value="all_or_nothing">{t("bank.editor.scoringAll")}</option>
              <option value="partial">{t("bank.editor.scoringPartial")}</option>
            </select>
          </label>
        )}
      </div>
    </div>
  );
}
