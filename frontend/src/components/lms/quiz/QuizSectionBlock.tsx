"use client";

import React from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { ItemOut, SectionOut } from "@/lib/lms/assessmentTypes";
import type { DraftOut } from "@/lib/lms/quizEditorTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { Button, IconButton } from "@/components/ui";
import { useDragReorder } from "@/components/lms/assessments/useDragReorder";
import { AddAtEnd, AddBetween } from "./AddBetween";
import { PassageCard } from "./PassageCard";
import { PickCard } from "./PickCard";
import { QuestionCard } from "./QuestionCard";
import { draftKey, itemKey, type QuizCtx, type QuizOps } from "./quizCtx";

type Entry = { kind: "item"; item: ItemOut; index: number } | { kind: "draft"; draft: DraftOut };

/** Items of a section with its new-card drafts placed after their `after_item_id` (at the end when null or gone). */
export function sectionEntries(section: SectionOut, drafts: DraftOut[]): Entry[] {
  const fresh = drafts.filter((d) => !d.item_id && d.section_id === section.id);
  const ids = new Set(section.items.map((i) => i.id));
  const out: Entry[] = [];
  section.items.forEach((item, index) => {
    out.push({ kind: "item", item, index });
    fresh.filter((d) => d.after_item_id === item.id).forEach((draft) => out.push({ kind: "draft", draft }));
  });
  fresh.filter((d) => !d.after_item_id || !ids.has(d.after_item_id)).forEach((draft) => out.push({ kind: "draft", draft }));
  return out;
}

/** Section name: its title, its key's label, else "Section N" (N = its place in the quiz). */
export function quizSectionName(s: SectionOut, index: number, uiLang: Lang, defLang: Lang, t: (k: string, p?: Record<string, string | number>) => string): string {
  const title = pickLocalized(s.title, uiLang, defLang);
  if (title) return title;
  if (s.key) {
    const l = t(`sections.${s.key}`);
    return l === `sections.${s.key}` ? s.key : l;
  }
  return t("assessments.section.n", { n: index + 1 });
}

/**
 * One section of the quiz editor. A quiz with one section shows no section header at all (7c-6: the default section
 * is hidden); with two or more, each section has its header ("Section 1" for the untitled first one).
 */
export function QuizSectionBlock({
  ctx, ops, section, index, count, showHeader, labels, structureLocked, lockedNote, onEdit, onDelete, onMoveBy,
}: {
  ctx: QuizCtx;
  ops: QuizOps;
  section: SectionOut;
  index: number;
  count: number;
  showHeader: boolean;
  labels: Map<string, string>;
  structureLocked: boolean;
  lockedNote: string;
  onEdit: () => void;
  onDelete: () => void;
  onMoveBy: (d: number) => void;
}) {
  const { lang, t } = useTranslation();
  const drafts = ctx.a.drafts ?? [];
  const entries = sectionEntries(section, drafts);
  const name = quizSectionName(section, index, lang, ctx.defaultLanguage, t);
  const drag = useDragReorder((f, to) => void ops.moveItem(section, f, to), ctx.canEdit && ops.openKey === null);
  const moveTargets = ctx.a.sections.filter((s) => s.id !== section.id)
    .map((s) => ({ id: s.id, label: quizSectionName(s, ctx.a.sections.indexOf(s), lang, ctx.defaultLanguage, t) }));
  const n = section.items.length;

  const body = (
    <>
      {entries.length === 0 && (
        <p className="rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-6 text-center text-sm text-slate-600">
          {t("quizEditor.section.empty")}
        </p>
      )}
      <ul className="space-y-2">
        {entries.map((e) => {
          if (e.kind === "draft") {
            const key = draftKey(e.draft.id);
            return (
              <li key={key}>
                <QuestionCard ctx={ctx} section={section} draft={e.draft} label={t("quizEditor.card.newQuestion")}
                  open={ops.openKey === key} onOpen={() => ops.requestOpen(key)} onClosed={ops.closed} actions={{}} />
              </li>
            );
          }
          const { item, index: i } = e;
          const key = itemKey(item.id);
          const moveUp = i > 0 ? () => void ops.moveItem(section, i, i - 1) : undefined;
          const moveDown = i < n - 1 ? () => void ops.moveItem(section, i, i + 1) : undefined;
          return (
            <li key={key} className="space-y-2">
              {item.kind === "question" && (
                <QuestionCard ctx={ctx} section={section} item={item} draft={drafts.find((d) => d.item_id === item.id)}
                  label={labels.get(item.id) ?? ""} open={ops.openKey === key} onOpen={() => ops.requestOpen(key)} onClosed={ops.closed}
                  dragProps={drag(i)}
                  actions={{
                    onMoveUp: moveUp, onMoveDown: moveDown,
                    onDelete: () => void ops.deleteItem(section, item, i),
                    onDuplicate: (p) => void ops.addQuestion(section, item.id, p),
                    moveTargets, onMoveToSection: (sid) => void ops.moveToSection(item, sid),
                  }} />
              )}
              {item.kind === "passage" && (
                <PassageCard ctx={ctx} ops={ops} section={section} item={item} index={i} count={n} labels={labels} drafts={drafts} dragProps={drag(i)} />
              )}
              {item.kind === "pick" && <PickCard ctx={ctx} ops={ops} section={section} item={item} index={i} count={n} dragProps={drag(i)} />}
              {ctx.canEdit && i < n - 1 && <AddBetween ops={ops} section={section} afterItemId={item.id} />}
            </li>
          );
        })}
      </ul>
      {ctx.canEdit && <AddAtEnd ops={ops} section={section} />}
    </>
  );

  if (!showHeader) return <div className="space-y-3">{body}</div>;
  return (
    <section aria-label={name} className="space-y-3 rounded-2xl border border-slate-200 bg-slate-50/60 p-3">
      <div className="flex flex-wrap items-start gap-x-2 gap-y-2">
        <div className="min-w-0 flex-1 basis-[12rem]">
          <h2 className="break-words text-lg font-semibold text-slate-900">{name}</h2>
          <p className="text-sm text-slate-600">
            {t("assessments.section.itemCount", { n })}
            {section.rules.allowed_types?.length ? ` · ${section.rules.allowed_types.map((q) => t(`bank.types.${q}.name`)).join(", ")}` : ""}
          </p>
        </div>
        {ctx.canEdit && (
          <div className="flex flex-wrap items-center gap-2">
            <IconButton variant="secondary" icon={<ArrowUp />} aria-label={t("assessments.section.up")} disabled={index === 0 || structureLocked}
              title={structureLocked ? lockedNote : undefined} onClick={() => onMoveBy(-1)} />
            <IconButton variant="secondary" icon={<ArrowDown />} aria-label={t("assessments.section.down")} disabled={index === count - 1 || structureLocked}
              title={structureLocked ? lockedNote : undefined} onClick={() => onMoveBy(1)} />
            <Button variant="secondary" size="sm" onClick={onEdit}>{t("assessments.section.edit")}</Button>
            <Button variant="dangerOutline" size="sm" disabled={structureLocked} title={structureLocked ? lockedNote : undefined} onClick={onDelete}>
              {t("assessments.section.delete")}
            </Button>
          </div>
        )}
      </div>
      {body}
    </section>
  );
}
