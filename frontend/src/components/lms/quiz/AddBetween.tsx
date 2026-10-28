"use client";

import React from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { SectionOut } from "@/lib/lms/assessmentTypes";
import { Button, MenuButton, type MenuItem } from "@/components/ui";
import type { QuizOps } from "./quizCtx";

function useAddItems(withQuestion: boolean): MenuItem[] {
  const { t } = useTranslation();
  const items: MenuItem[] = [
    { id: "find", label: t("quizEditor.add.find"), description: t("quizEditor.add.findHint") },
    { id: "passage", label: t("quizEditor.add.passage"), description: t("quizEditor.add.passageHint") },
    { id: "pick", label: t("quizEditor.add.pick"), description: t("quizEditor.add.pickHint") },
  ];
  return withQuestion ? [{ id: "question", label: t("quizEditor.add.question") }, ...items] : items;
}

function onPick(ops: QuizOps, section: SectionOut | null, after: string | null, id: string) {
  if (id === "question") void ops.addQuestion(section, after);
  else if (id === "find") ops.addFrom(section, after, "questions");
  else if (id === "passage") ops.addFrom(section, after, "passage");
  else if (id === "pick") ops.addFrom(section, after, "pick");
}

/** The small "+" between two cards (44 px target): new question, find questions, passage, random group, placed here. */
export function AddBetween({ ops, section, afterItemId }: { ops: QuizOps; section: SectionOut; afterItemId: string }) {
  const { t } = useTranslation();
  const items = useAddItems(true);
  return (
    <div className="flex justify-center">
      <MenuButton variant="secondary" size="sm" align="start" className="w-auto" items={items}
        onSelect={(id) => onPick(ops, section, afterItemId, id)}
        label={<><Plus className="h-4 w-4" aria-hidden="true" /><span className="sr-only">{t("quizEditor.card.addBetween")}</span></>} />
    </div>
  );
}

/** End of a section: "+ New question" and the other ways to add (Canvas: New question, Find questions). */
export function AddAtEnd({ ops, section, disabled, primary = false }: {
  ops: QuizOps; section: SectionOut | null; disabled?: boolean;
  /** Phase 7c UX: "New question" is the primary action (the empty quiz). */
  primary?: boolean;
}) {
  const { t } = useTranslation();
  const items = useAddItems(false);
  return (
    <div className="flex flex-wrap gap-2 [&>*]:flex-1 sm:[&>*]:flex-none">
      <Button variant={primary ? "primary" : "secondary"} disabled={disabled} leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}
        onClick={() => void ops.addQuestion(section, null)}>{t("quizEditor.card.addQuestion")}</Button>
      <MenuButton variant="secondary" align="start" disabled={disabled} items={items} label={t("quizEditor.add.more")}
        onSelect={(id) => onPick(ops, section, null, id)} />
    </div>
  );
}
