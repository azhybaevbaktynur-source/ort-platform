"use client";

// Phase 7a S5: "New assignment" (PHASE_7A_DESIGN 5): kind radios; text / file / offline ask for points and a due
// date; a quiz shows the fields of the existing "New assessment" dialog (preset radios, subject, languages) and is
// created through the same POST in one transaction (section 3.1). Details are edited on the next page.
import React, { useEffect, useId, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { createAssignment } from "@/lib/lms/assignments";
import type { AssignmentKind, AssignmentStaffOut } from "@/lib/lms/assignmentTypes";
import type { AssessmentPreset } from "@/lib/lms/assessmentTypes";
import { LEGACY_UI, useTemplateUi } from "@/lib/lms/templates";
import { cleanLocalized } from "@/lib/lms/localized";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { fromLocalInput } from "@/components/lms/assessments/format";
import { Button, Checkbox, Dialog, FieldLabel, Input, Select, cn, focusRing } from "@/components/ui";
import { AssignmentError, KindIcon, parsePoints } from "./assignmentUi";

const KINDS: AssignmentKind[] = ["text", "file", "none", "quiz"];

export function AssignmentEditorDialog({ open, onCreated, onCancel }: {
  open: boolean;
  onCreated: (a: AssignmentStaffOut) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const { course } = useCourse();
  const ui = useTemplateUi();
  const uid = useId().replace(/:/g, "");
  const courseLanguages = course.languages;
  const defaultLanguage = course.default_language;
  const presets = ui.assessmentPresets;
  const ortCourse = ui.key === "ort" || ui === LEGACY_UI;
  const subjects = ui.subjectKeys;
  const firstSubject = subjects[0] ?? "";

  const [kind, setKind] = useState<AssignmentKind>("text");
  const [title, setTitle] = useState<LocalizedText>({});
  const [points, setPoints] = useState("10");
  const [due, setDue] = useState("");
  const [preset, setPreset] = useState<AssessmentPreset>("none");
  const [languages, setLanguages] = useState<Lang[]>([defaultLanguage]);
  const [subject, setSubject] = useState(firstSubject);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (open) {
      setKind("text"); setTitle({}); setPoints("10"); setDue(""); setPreset("none"); setLanguages([defaultLanguage]);
      setSubject(firstSubject); setError(null); setTouched(false);
    }
  }, [open, defaultLanguage, firstSubject]);

  const cleaned = cleanLocalized(title, courseLanguages);
  const titleOk = Object.keys(cleaned).length > 0;
  const pts = parsePoints(points);
  const pointsOk = kind === "quiz" || (pts !== null && !Number.isNaN(pts) && pts >= 0 && pts <= 10000);
  const valid = titleOk && pointsOk;

  const toggleLang = (l: Lang) =>
    setLanguages((cur) => (cur.includes(l) ? (cur.length > 1 ? cur.filter((x) => x !== l) : cur) : courseLanguages.filter((x) => cur.includes(x) || x === l)));

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setTouched(true);
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      const out = await createAssignment(course.id, kind === "quiz"
        ? { kind, title: cleaned, quiz: { preset, languages, ...(preset === "ort_subject" ? { subject_key: subject } : {}) } }
        : { kind, title: cleaned, points_possible: pts, due_at: fromLocalInput(due) });
      onCreated(out);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const formId = `${uid}-form`;
  return (
    <Dialog open={open} onClose={onCancel} busy={busy} size="lg" title={t("assignments.create.title")}
      description={t("assignments.create.subtitle")}
      footer={(
        <>
          <Button variant="secondary" disabled={busy} onClick={onCancel}>{t("ui.cancel")}</Button>
          <Button type="submit" form={formId} loading={busy}>{kind === "quiz" ? t("assignments.create.submitQuiz") : t("assignments.create.submit")}</Button>
        </>
      )}>
      <form id={formId} onSubmit={(e) => void submit(e)} className="space-y-5">
        <fieldset>
          <legend className="text-sm font-medium leading-6 text-slate-800">{t("assignments.create.kind")}</legend>
          <div className="mt-1 grid gap-2 sm:grid-cols-2">
            {KINDS.map((k) => (
              <label key={k} className={cn("flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border px-3 py-2.5",
                kind === k ? "border-brand-500 bg-brand-50" : "border-slate-200 hover:bg-slate-50", "focus-within:ring-2 focus-within:ring-brand-600")}>
                <input type="radio" name={`${uid}-kind`} className="mt-1 h-4 w-4 accent-brand-600" checked={kind === k} onChange={() => setKind(k)} />
                <span className="min-w-0">
                  <span className="flex items-center gap-1.5 font-medium text-slate-900"><KindIcon kind={k} />{t(`assignments.kinds.${k}`)}</span>
                  <span className="block text-sm leading-5 text-slate-600">{t(`assignments.kindHints.${k}`)}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <div>
          <LocalizedTextInput label={t("assignments.create.titleLabel")} languages={courseLanguages} defaultLanguage={defaultLanguage}
            value={title} onChange={setTitle} maxLength={200} required />
          {touched && !titleOk && <p className="mt-1 text-sm text-danger-700">{t("assignments.create.titleRequired")}</p>}
        </div>

        {kind !== "quiz" ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label={t("assignments.fields.points")} inputMode="decimal" value={points} onChange={(e) => setPoints(e.target.value)}
              hint={t("assignments.fields.pointsHint")} error={touched && !pointsOk ? t("assignments.fields.pointsInvalid") : undefined} />
            <Input type="datetime-local" label={t("assignments.fields.due")} optional value={due} onChange={(e) => setDue(e.target.value)} />
          </div>
        ) : (
          <div className="space-y-4">
            {presets.length > 1 && (
              <fieldset>
                <legend className="text-sm font-medium leading-6 text-slate-800">{t("assessments.create.preset")}</legend>
                <div className="mt-1 space-y-2">
                  {presets.map((p) => (
                    <label key={p} className={cn("flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border border-slate-200 px-3 py-2", focusRing)}>
                      <input type="radio" name={`${uid}-preset`} className="mt-1 h-4 w-4 accent-brand-600" checked={preset === p} onChange={() => setPreset(p)} />
                      <span>
                        <span className="font-medium text-slate-900">{t(`assessments.presets.${p}.name`)}</span>
                        <span className="block text-sm text-slate-600">{t(`assessments.presets.${p}.hint`)}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
            {preset === "ort_subject" && (
              <Select label={t("assessments.create.subject")} value={subject} onChange={(e) => setSubject(e.target.value)}
                options={subjects.map((k) => ({ value: k, label: t(`sections.${k}`) }))} />
            )}
            <fieldset>
              <FieldLabel>{t("assessments.create.languages")}</FieldLabel>
              <div className="flex flex-wrap gap-x-4">
                {courseLanguages.map((l) => (
                  <Checkbox key={l} label={t(`courses.languages.${l}`)} checked={languages.includes(l)} onChange={() => toggleLang(l)} />
                ))}
              </div>
              <p className="text-sm text-slate-600">{t(ortCourse ? "assessments.create.languagesHint" : "assessments.create.languagesHintGeneral")}</p>
            </fieldset>
            <p className="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700">{t("assignments.create.quizNext")}</p>
          </div>
        )}
        <AssignmentError error={error} />
      </form>
    </Dialog>
  );
}
