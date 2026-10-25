"use client";

import React, { useState } from "react";
import { ArrowDown, ArrowUp, GripVertical } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { reorderItems } from "@/lib/lms/assessments";
import type { AssessmentStaffOut, SectionOut } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { btnDanger, btnSecondary, btnSmall } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { EmptyState } from "@/components/ui";
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
  section, assessment, ctx, index, count, defaultLanguage, onMoveBy, onEdit, onDelete, onAdd, dragProps, structureLocked = false,
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
  /** Phase 6 S4b: locked course template: reorder and delete are disabled (never hidden), design §5.4. */
  structureLocked?: boolean;
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
      {/* Phase 6b S5c (UX T7): title and actions wrap; on phones the actions take their own row under the title. */}
      <div className="mb-3 flex flex-wrap items-start gap-x-2 gap-y-2">
        {ctx.canEdit && !structureLocked && <GripVertical className="mt-1 h-4 w-4 shrink-0 cursor-grab text-slate-400" aria-hidden="true" />}
        <div className="min-w-0 flex-1 basis-[12rem]">
          <h3 className="break-words font-semibold text-slate-900">{index + 1}. {sectionName(section, lang, defaultLanguage, t)}</h3>
          <p className="text-sm text-slate-600">
            {t("assessments.section.itemCount", { n: section.items.length })}
            {section.time_limit_s ? ` · ${t("assessments.student.minutes", { n: Math.round(section.time_limit_s / 60) })}` : assessment.navigation === "section_forward_only" ? ` · ${t("assessments.section.untimed")}` : ""}
            {section.rules.allowed_types?.length ? ` · ${section.rules.allowed_types.map((q) => t(`bank.types.${q}.name`)).join(", ")}` : ""}
          </p>
        </div>
        {ctx.canEdit && (
          <div className="flex basis-full flex-wrap items-center gap-1.5 sm:basis-auto">
            <button type="button" className={btnSmall} disabled={index === 0 || structureLocked} aria-label={t("assessments.section.up")} title={structureLocked ? t("templates.lockedNote") : undefined} onClick={() => onMoveBy(-1)}><ArrowUp className="h-4 w-4" aria-hidden="true" /></button>
            <button type="button" className={btnSmall} disabled={index === count - 1 || structureLocked} aria-label={t("assessments.section.down")} title={structureLocked ? t("templates.lockedNote") : undefined} onClick={() => onMoveBy(1)}><ArrowDown className="h-4 w-4" aria-hidden="true" /></button>
            <button type="button" className={btnSmall} onClick={onEdit}>{t("assessments.section.edit")}</button>
            <button type="button" className={btnDanger} disabled={structureLocked} title={structureLocked ? t("templates.lockedNote") : undefined} onClick={onDelete}>{t("assessments.section.delete")}</button>
          </div>
        )}
      </div>
      {section.items.length === 0 ? (
        // Phase 6b S5c (UX T24): the empty section carries its own next step.
        <EmptyState className="mb-1 py-6" title={t("assessments.section.empty")}
          action={ctx.canEdit ? <button type="button" className={btnSecondary} onClick={onAdd}>{t("assessments.section.addItems")}</button> : undefined} />
      ) : (
        <ul className="mb-3 space-y-2">
          {section.items.map((it, i) => (
            <ItemRow key={it.id} item={it} ctx={itemCtx} index={i} count={section.items.length}
              onMoveBy={(d) => void moveItem(i, i + d)} dragProps={drag(i)} />
          ))}
        </ul>
      )}
      {ctx.canEdit && section.items.length > 0 && <button type="button" className={btnSecondary} onClick={onAdd}>{t("assessments.section.addItems")}</button>}
    </section>
  );
}
