"use client";

import React from "react";
import { ArrowDown, ArrowUp, BookOpen, GripVertical } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { ItemOut, SectionOut } from "@/lib/lms/assessmentTypes";
import type { DraftOut } from "@/lib/lms/quizEditorTypes";
import { Button, IconButton } from "@/components/ui";
import { QuestionCard } from "./QuestionCard";
import { itemKey, type QuizCtx, type QuizOps } from "./quizCtx";

/** A passage block: its header and the indented question cards of its children (PHASE_7C_DESIGN 8.2). */
export function PassageCard({
  ctx, ops, section, item, index, count, labels, drafts, dragProps,
}: {
  ctx: QuizCtx;
  ops: QuizOps;
  section: SectionOut;
  item: ItemOut;
  index: number;
  count: number;
  labels: Map<string, string>;
  drafts: DraftOut[];
  dragProps?: React.HTMLAttributes<HTMLElement>;
}) {
  const { t } = useTranslation();
  const children = item.children ?? [];
  const draggable = !!dragProps && Object.keys(dragProps).length > 0;
  return (
    <div {...dragProps} className="rounded-2xl border border-slate-200 bg-slate-50 p-3 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {draggable && <GripVertical className="hidden h-4 w-4 shrink-0 cursor-grab text-slate-400 sm:block" aria-hidden="true" />}
        <BookOpen className="h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
        <p className="min-w-0 flex-1 basis-[12rem] break-words font-semibold text-slate-900">
          {t("assessments.item.passage")}: {item.passage?.title || t("assessments.untitled")}
          <span className="ml-2 text-sm font-normal text-slate-600">{t("assessments.item.children", { n: children.length })}</span>
        </p>
        {ctx.canEdit && (
          <div className="flex flex-wrap items-center gap-2">
            <IconButton variant="secondary" icon={<ArrowUp />} aria-label={t("quizEditor.card.moveUp")} disabled={index === 0}
              onClick={() => void ops.moveItem(section, index, index - 1)} />
            <IconButton variant="secondary" icon={<ArrowDown />} aria-label={t("quizEditor.card.moveDown")} disabled={index === count - 1}
              onClick={() => void ops.moveItem(section, index, index + 1)} />
            <Button variant="dangerOutline" size="sm" onClick={() => void ops.deleteItem(section, item, index)}>{t("quizEditor.passage.remove")}</Button>
          </div>
        )}
      </div>
      <ul className="space-y-2 border-l-2 border-slate-200 pl-3">
        {children.map((c, i) => (
          <li key={c.id}>
            <QuestionCard ctx={ctx} section={section} item={c} draft={drafts.find((d) => d.item_id === c.id)}
              label={labels.get(c.id) ?? ""} childOf={item}
              open={ops.openKey === itemKey(c.id)} onOpen={() => ops.requestOpen(itemKey(c.id))} onClosed={ops.closed}
              actions={{
                onMoveUp: i > 0 ? () => void ops.moveChild(section, item, i, i - 1) : undefined,
                onMoveDown: i < children.length - 1 ? () => void ops.moveChild(section, item, i, i + 1) : undefined,
                onDelete: () => void ops.deleteItem(section, c, i, item),
              }} />
          </li>
        ))}
      </ul>
    </div>
  );
}
