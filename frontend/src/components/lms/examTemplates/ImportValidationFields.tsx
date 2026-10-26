"use client";

// Phase 7b S4: import dialog block (PHASE_7B_DESIGN 8, 10): "Validate against exam" (draft exams of the course that
// were created from a template) and "Add imported questions to this exam". Offered for the general format only.
import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { listAssessments } from "@/lib/lms/assessments";
import type { AssessmentExamTemplateRef, AssessmentStaffSummaryOut } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { Checkbox, Select } from "@/components/ui";

type Summary = AssessmentStaffSummaryOut & { exam_template?: AssessmentExamTemplateRef | null };

/** Draft, blank-or-template exams; when the list carries `exam_template`, only template ones. */
function candidates(rows: Summary[]): Summary[] {
  const drafts = rows.filter((r) => r.status === "draft" && r.preset === "none" && !r.deleted_at);
  const knowsTemplate = rows.some((r) => "exam_template" in r);
  return knowsTemplate ? drafts.filter((r) => !!r.exam_template) : drafts;
}

export function ImportValidationFields({ courseId, value, attach, disabled, onChange }: {
  courseId: string;
  value: string;
  attach: boolean;
  disabled?: boolean;
  onChange: (assessmentId: string, attach: boolean) => void;
}) {
  const { lang, t } = useTranslation();
  const [rows, setRows] = useState<Summary[] | null>(null);

  useEffect(() => {
    let alive = true;
    listAssessments(courseId, { limit: 100 })
      .then((p) => { if (alive) setRows(candidates(p.items as Summary[])); })
      .catch(() => { if (alive) setRows([]); /* optional: importing without validation still works */ });
    return () => { alive = false; };
  }, [courseId]);

  if (!rows || rows.length === 0) return null;
  const label = (r: Summary) => {
    const name = pickLocalized(r.title, lang, r.languages[0]) || t("assessments.untitled");
    return r.exam_template ? `${name} · ${t("examTemplates.versionShort", { n: r.exam_template.version_no })}` : name;
  };
  return (
    <div className="space-y-2">
      <Select label={t("examTemplates.import.validateAgainst")} value={value} disabled={disabled}
        hint={t("examTemplates.import.validateHint")}
        onChange={(e) => onChange(e.target.value, e.target.value ? attach : false)}>
        <option value="">{t("examTemplates.import.noValidation")}</option>
        {rows.map((r) => <option key={r.id} value={r.id}>{label(r)}</option>)}
      </Select>
      {value && (
        <Checkbox label={t("examTemplates.import.attach")} hint={t("examTemplates.import.attachHint")} checked={attach} disabled={disabled}
          onChange={(e) => onChange(value, e.target.checked)} />
      )}
    </div>
  );
}
