"use client";

// Phase 8b S4: Scoring tab (PHASE_8B_DESIGN 9.1): the scheme picker (from the blocks catalog), the Phase 4 live
// preview table of the chosen scheme version, and the result page choice.
import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { BlocksOut, BlockSchemeVersionOut, ExamTemplateScope } from "@/lib/lms/examTemplateTypes";
import { getScheme } from "@/lib/lms/grading";
import type { SchemeVersionOut } from "@/lib/lms/gradingTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { SchemePreview } from "@/components/lms/grading/schemes/SchemePreview";
import { Card, ErrorState, LoadingState, Select } from "@/components/ui";
import { RadioCards, fieldId, type FieldErr, type Update } from "./parts";
import type { SpecDraft } from "./specDraft";

export function schemeTitle(s: BlockSchemeVersionOut, lang: Lang): string {
  return typeof s.title === "string" ? s.title : pickLocalized(s.title, lang) || s.id;
}

/** Raw-score maximum for the preview: the sum of the sections' "At most" when every section has one, else 100. */
function possibleOf(d: SpecDraft): number {
  if (!d.sections.length) return 100;
  let sum = 0;
  for (const s of d.sections) {
    const n = Number(s.maxItems.trim());
    if (!s.maxItems.trim() || !Number.isInteger(n) || n < 1) return 100;
    sum += n;
  }
  return sum;
}

export function ScoringTab({ draft, update, readOnly, err, blocks, scope }: {
  draft: SpecDraft;
  update: Update;
  readOnly: boolean;
  err: FieldErr;
  blocks: BlocksOut;
  scope: ExamTemplateScope;
}) {
  const { lang, t } = useTranslation();
  const rows = blocks.scheme_versions;
  const chosen = rows.find((s) => s.id === draft.schemeId) ?? null;
  const groups: { scope: BlockSchemeVersionOut["scope"]; rows: BlockSchemeVersionOut[] }[] = (["system", "mine"] as const)
    .map((sc) => ({ scope: sc, rows: rows.filter((r) => r.scope === sc) }))
    .filter((g) => g.rows.length > 0);

  return (
    <div className="space-y-6">
      <Card title={t("examTemplates.constructor.scoring.title")} description={t("examTemplates.constructor.scoring.body")}>
        <div className="space-y-4">
          <Select id={fieldId("scoring")} label={t("examTemplates.editor.scheme")} value={draft.schemeId} disabled={readOnly}
            hint={t(scope === "teacher" ? "examTemplates.editor.schemeHintTeacher" : "examTemplates.editor.schemeHintShared")}
            error={err("scoring")} onChange={(e) => update((d) => ({ ...d, schemeId: e.target.value }))}>
            <option value="">{t("examTemplates.constructor.scoring.noScheme")}</option>
            {draft.schemeId && !chosen && <option value={draft.schemeId}>{t("examTemplates.editor.schemeCurrent")}</option>}
            {groups.map((g) => (
              <optgroup key={g.scope} label={t(`examTemplates.constructor.scoring.group.${g.scope}`)}>
                {g.rows.map((s) => <option key={s.id} value={s.id}>{schemeTitle(s, lang)}</option>)}
              </optgroup>
            ))}
          </Select>
          {chosen ? <SchemeLivePreview scheme={chosen} possible={possibleOf(draft)} />
            : <p className="text-sm text-slate-600">{t(draft.schemeId ? "examTemplates.constructor.scoring.previewUnavailable" : "examTemplates.constructor.scoring.pointsOnly")}</p>}
        </div>
      </Card>

      <Card title={t("examTemplates.editor.resultView")}>
        <RadioCards id={fieldId("result_view")} legend={t("examTemplates.constructor.resultView.legend")} value={draft.resultView}
          disabled={readOnly} error={err("result_view")} onChange={(v) => update((d) => ({ ...d, resultView: v }))}
          options={[
            { value: "", label: t("examTemplates.editor.courseDefault"), description: t("examTemplates.constructor.resultView.inherit") },
            ...blocks.result_views.map((r) => ({
              value: r, label: t(`examTemplates.blocks.resultViews.${r}`), description: t(`examTemplates.constructor.resultView.body.${r}`),
            })),
          ]} />
      </Card>
    </div>
  );
}

function SchemeLivePreview({ scheme, possible }: { scheme: BlockSchemeVersionOut; possible: number }) {
  const { t } = useTranslation();
  const [version, setVersion] = useState<SchemeVersionOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    setVersion(null);
    setError(null);
    getScheme(scheme.scheme_id)
      .then((s) => {
        if (!alive) return;
        const v = s.versions.find((x) => x.version_no === scheme.version_no) ?? null;
        if (v) setVersion(v); else setError({ code: "not_found" });
      })
      .catch((e) => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [scheme.scheme_id, scheme.version_no, attempt]);

  return (
    <section aria-labelledby="tpl-scheme-preview" className="space-y-2">
      <h3 id="tpl-scheme-preview" className="text-base font-semibold text-slate-900">{t("examTemplates.constructor.scoring.previewTitle")}</h3>
      <p className="text-sm text-slate-600">{t("examTemplates.constructor.scoring.previewPossible", { n: possible })}</p>
      {error ? <ErrorState variant="inline" message={t("examTemplates.constructor.scoring.previewError")} onRetry={() => setAttempt((n) => n + 1)} />
        : !version ? <LoadingState rows={2} />
          : <SchemePreview key={`${version.id}-${possible}`} type={version.type} params={version.params} blocked={false} defaultPossible={possible} />}
    </section>
  );
}
