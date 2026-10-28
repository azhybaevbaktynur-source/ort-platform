"use client";

import React, { useEffect, useId, useRef, useState } from "react";
import { ArrowDown, ArrowUp, ImagePlus, MoreHorizontal, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { MenuButton } from "@/components/ui";
import { ImagePicker } from "../ImagePicker";
import { RichTextField } from "../RichTextField";
import { inputCls, labelCls } from "../ui";
import { btnSmall } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { nextChoiceId, type ChoiceForm, type QuestionForm } from "./formModel";

/** single_choice and multiple_answers: choices with letters as ids, mark correct, reorder, optional images. */
export function ChoiceFields({
  courseId, form, onChange, disabled, keyboardAnswers = false, compact = false, error = null, errorKey = null,
}: {
  courseId: string; form: QuestionForm; onChange: (patch: Partial<QuestionForm>) => void; disabled?: boolean;
  /** Phase 7c S5 (the quiz card only; default off, so the Bank tab and ORT screens are unchanged): Enter in an answer
   * goes to the next answer and adds one after the last; Backspace in an empty answer removes it. */
  keyboardAnswers?: boolean;
  /** Phase 7c UX (the quiz card only; default off): one line per answer (correct mark, letter, growing text, actions);
   * the image picker opens from a small "Add image" action and stays shown while an image is set. */
  compact?: boolean;
  /** Phase 7c UX (the quiz card only): the validation error of the answers, shown under them; `errorKey` (its i18n key,
   * client-side checks) says which answer controls are marked invalid. */
  error?: string | null;
  errorKey?: string | null;
}) {
  const { t } = useTranslation();
  const errId = `${useId()}-answers-err`;
  const [imageOpen, setImageOpen] = useState<Set<string>>(new Set());
  const fields = useRef(new Map<string, HTMLTextAreaElement | null>());
  const focusNext = useRef<string | null>(null);
  useEffect(() => {
    const id = focusNext.current;
    if (!id) return;
    const el = fields.current.get(id);
    if (el) { focusNext.current = null; el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
  });
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
  const onAnswerKey = (i: number) => (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!keyboardAnswers || disabled || e.nativeEvent.isComposing) return;
    const c = form.choices[i];
    if (e.key === "Enter" && !e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      if (i < form.choices.length - 1) { fields.current.get(form.choices[i + 1].id)?.focus(); return; }
      if (form.choices.length >= 10) return;
      const id = nextChoiceId(form.choices);
      focusNext.current = id;
      setChoices([...form.choices, { id, text: "", image: null }]);
    } else if (e.key === "Backspace" && c.text === "" && !c.image && form.choices.length > 2) {
      e.preventDefault();
      focusNext.current = (form.choices[i - 1] ?? form.choices[i + 1]).id;
      remove(i);
    }
  };
  const toggleMulti = (id: string) =>
    onChange({ correctMulti: form.correctMulti.includes(id) ? form.correctMulti.filter((x) => x !== id) : [...form.correctMulti, id] });

  // Which control the answers' error belongs to (marked invalid and described by the message).
  const emptyBad = errorKey === "bank.editor.errChoiceEmpty";
  const correctBad = errorKey === "bank.editor.errCorrect";
  const listBad = !!error && !emptyBad && !correctBad;

  if (compact) {
    return (
      <div className="space-y-2">
        <span className={labelCls}>{t("bank.editor.choices")}</span>
        <ul className="space-y-2">
          {form.choices.map((c, i) => {
            const checked = multi ? form.correctMulti.includes(c.id) : form.correctSingle === c.id;
            const showImage = !!c.image || imageOpen.has(c.id);
            const answerBad = (emptyBad && !c.text.trim() && !c.image) || (listBad && i === 0);
            const actions = (id: string) => {
              if (id === "image") setImageOpen((s) => new Set(s).add(c.id));
              else if (id === "up") move(i, -1);
              else if (id === "down") move(i, 1);
              else if (id === "remove") remove(i);
            };
            return (
              <li key={c.id} className={`rounded-xl border px-2 py-1.5 ${checked ? "border-emerald-300 bg-emerald-50/40" : "border-slate-200"}`}>
                <div className="flex items-start gap-2">
                  <label className="flex min-h-11 shrink-0 cursor-pointer items-center gap-1.5 sm:min-h-10">
                    <input type={multi ? "checkbox" : "radio"} name="correct-choice" disabled={disabled} checked={checked}
                      className="h-5 w-5 accent-emerald-600"
                      aria-label={t("quizEditor.card.markCorrect", { letter: c.id })}
                      aria-invalid={correctBad && i === 0 ? true : undefined} aria-describedby={correctBad ? errId : undefined}
                      onChange={() => (multi ? toggleMulti(c.id) : onChange({ correctSingle: c.id }))} />
                    <span aria-hidden="true" className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 text-sm font-bold text-slate-700">{c.id}</span>
                  </label>
                  <div className="min-w-0 flex-1">
                    <RichTextField rows={1} autoGrow smartPreview toolbarOnFocus value={c.text} disabled={disabled}
                      onChange={(v) => update(i, { text: v })}
                      invalid={answerBad} describedBy={answerBad ? errId : undefined}
                      ariaLabel={t("quizEditor.card.answerLabel", { letter: c.id })}
                      inputRef={(el: HTMLTextAreaElement | null) => { fields.current.set(c.id, el); }}
                      {...(keyboardAnswers ? { onKeyDown: onAnswerKey(i) } : {})} />
                  </div>
                  <span className="hidden shrink-0 gap-1 sm:flex">
                    {!showImage && (
                      <button type="button" disabled={disabled} className={btnSmall} onClick={() => actions("image")} aria-label={t("quizEditor.card.addImageTo", { letter: c.id })} title={t("quizEditor.card.addImage")}>
                        <ImagePlus className="h-4 w-4" aria-hidden="true" />
                      </button>
                    )}
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
                  <MenuButton variant="secondary" size="sm" align="end" disabled={disabled} className="shrink-0 sm:hidden" onSelect={actions}
                    label={<><MoreHorizontal className="h-4 w-4" aria-hidden="true" /><span className="sr-only">{t("quizEditor.card.answerActions", { letter: c.id })}</span></>}
                    items={[
                      ...(!showImage ? [{ id: "image", label: t("quizEditor.card.addImage") }] : []),
                      { id: "up", label: t("bank.editor.moveUp"), disabled: i === 0 },
                      { id: "down", label: t("bank.editor.moveDown"), disabled: i === form.choices.length - 1 },
                      { id: "remove", label: t("bank.editor.removeChoice"), disabled: form.choices.length <= 2 },
                    ]} />
                </div>
                {showImage && (
                  <div className="mt-1.5 sm:pl-[4.5rem]">
                    <ImagePicker compact courseId={courseId} value={c.image} disabled={disabled} onChange={(img) => update(i, { image: img })} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        {error && <p id={errId} className="text-sm text-red-700">{error}</p>}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <button type="button" disabled={disabled || form.choices.length >= 10} className={btnSmall} onClick={add}
            aria-describedby={listBad ? errId : undefined}>
            <Plus className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" />{t("bank.editor.addChoice")}
          </button>
          {keyboardAnswers && <p className="min-w-0 flex-1 basis-[14rem] text-xs text-slate-500">{t("quizEditor.card.enterAdds")}</p>}
        </div>
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
              <RichTextField compact rows={2} value={c.text} disabled={disabled} onChange={(v) => update(i, { text: v })}
                {...(keyboardAnswers ? {
                  onKeyDown: onAnswerKey(i), ariaLabel: t("quizEditor.card.answerLabel", { letter: c.id }),
                  inputRef: (el: HTMLTextAreaElement | null) => { fields.current.set(c.id, el); },
                } : {})} />
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
      {keyboardAnswers && <p className="text-xs text-slate-500">{t("quizEditor.card.enterAdds")}</p>}
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
