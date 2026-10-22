"use client";

import React, { useState } from "react";
import { ArrowDown, ArrowUp, GripVertical } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { reorderItems } from "@/lib/lms/assessments";
import type { AssessmentStaffOut, SectionOut } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { btnDanger, btnPrimary, btnSmall } from "@/components/lms/content/ui";
import { ItemRow, type RowCtx } from "./ItemRow";
import { moveIndex } from "./format";
import { useDragReorder } from "./useDragReorder";

export function sectionName(s: SectionOut, uiLang: Lang, defLang: Lang, t: (k: string, p?: Record<string, string | number>) => string): string {
  const title = pickLocalized(s.title, uiLang, defLang);
  if (title) return title;
  if (s.key) {
    const l = t(`sections.${s.key}`);
    return l === `sections.${s.key}` ? s.key : l;
  }
  return t("assessments.section.n", { n: s.position });
}

export function SectionCard({
  section, assessment, ctx, index, count, defaultLanguage, onMoveBy, onEdit, onDelete, onAdd, dragProps,
}: {
  section: SectionOut;
  assessment: AssessmentStaffOut;
  ctx: RowCtx;
  index: number;
  count: number;
  defaultLanguage: Lang;
  onMoveBy: (delta: number) => void;
  onEdit: () => void;
  onDelete: () => void;
  onAdd: () => void;
  dragProps?: React.HTMLAttributes<HTMLElement>;
}) {
  const { lang, t } = useTranslation();
  const [reorderBusy, setReorderBusy] = useState(false);
  const itemCtx: RowCtx = { ...ctx, currentSectionId: section.id };

  const moveItem = async (from: number, to: number) => {
    const ids = moveIndex(section.items.map((i) => i.id), from, to);
    if (ids.every((id, k) => id === section.items[k].id)) return;
    setReorderBusy(true);
    try { await reorderItems(ctx.courseId, ctx.assessmentId, section.id, { item_ids: ids }); } catch (e) { ctx.onError(e); }
    try { await ctx.onChanged(); } finally { setReorderBusy(false); }
  };
  const drag = useDragReorder((f, to) => void moveItem(f, to), ctx.canEdit && !reorderBusy);

  return (
    <section {...dragProps} className="rounded-2xl border border-slate-200 bg-slate-50 p-3" aria-label={sectionName(section, lang, defaultLanguage, t)}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {ctx.canEdit && <GripVertical className="h-4 w-4 cursor-grab text-slate-400" aria-hidden="true" />}
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-slate-900">{index + 1}. {sectionName(section, lang, defaultLanguage, t)}</h3>
          <p className="text-xs text-slate-500">
            {t("assessments.section.itemCount", { n: section.items.length })}
            {section.time_limit_s ? ` · ${t("assessments.student.minutes", { n: Math.round(section.time_limit_s / 60) })}` : assessment.navigation === "section_forward_only" ? ` · ${t("assessments.section.untimed")}` : ""}
            {section.rules.allowed_types?.length ? ` · ${section.rules.allowed_types.map((q) => t(`bank.types.${q}.name`)).join(", ")}` : ""}
          </p>
        </div>
        {ctx.canEdit && (
          <div className="flex flex-wrap items-center gap-1">
            <button type="button" className={btnSmall} disabled={index === 0} aria-label={t("assessments.section.up")} onClick={() => onMoveBy(-1)}><ArrowUp className="h-3.5 w-3.5" aria-hidden="true" /></button>
            <button type="button" className={btnSmall} disabled={index === count - 1} aria-label={t("assessments.section.down")} onClick={() => onMoveBy(1)}><ArrowDown className="h-3.5 w-3.5" aria-hidden="true" /></button>
            <button type="button" className={btnSmall} onClick={onEdit}>{t("assessments.section.edit")}</button>
            <button type="button" className={btnDanger} onClick={onDelete}>{t("assessments.section.delete")}</button>
          </div>
        )}
      </div>
      {section.items.length === 0 ? (
        <p className="mb-3 text-sm text-slate-500">{t("assessments.section.empty")}</p>
      ) : (
        <ul className="mb-3 space-y-2">
          {section.items.map((it, i) => (
            <ItemRow key={it.id} item={it} ctx={itemCtx} index={i} count={section.items.length}
              onMoveBy={(d) => void moveItem(i, i + d)} dragProps={drag(i)} />
          ))}
        </ul>
      )}
      {ctx.canEdit && <button type="button" className={btnPrimary} onClick={onAdd}>{t("assessments.section.addItems")}</button>}
    </section>
  );
}
