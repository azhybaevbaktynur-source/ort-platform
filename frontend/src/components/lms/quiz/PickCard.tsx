"use client";

import React from "react";
import type { ItemOut, SectionOut } from "@/lib/lms/assessmentTypes";
import { ItemRow, type RowCtx } from "@/components/lms/assessments/ItemRow";
import type { QuizCtx, QuizOps } from "./quizCtx";

/**
 * A random group ("pick N from a bank"): the builder's item row (count, filter, pool sizes per language, points,
 * edit with PickFields, move, move to section, remove), shown as a card of the quiz editor.
 */
export function PickCard({
  ctx, ops, section, item, index, count, dragProps,
}: {
  ctx: QuizCtx;
  ops: QuizOps;
  section: SectionOut;
  item: ItemOut;
  index: number;
  count: number;
  dragProps?: React.HTMLAttributes<HTMLLIElement>;
}) {
  const rowCtx: RowCtx = {
    courseId: ctx.courseId, assessmentId: ctx.a.id, canEdit: ctx.canEdit, sections: ctx.a.sections,
    currentSectionId: section.id, onChanged: ctx.reload, onError: ctx.onError,
  };
  return (
    <ul className="[&>li]:rounded-2xl [&>li]:shadow-sm">
      <ItemRow item={item} ctx={rowCtx} index={index} count={count} dragProps={dragProps}
        onMoveBy={(d) => void ops.moveItem(section, index, index + d)} pickPointsPerQuestion />
    </ul>
  );
}
