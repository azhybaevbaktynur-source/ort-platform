"use client";

import React from "react";
import Link from "next/link";
import { ArrowDown, ArrowUp, ImageIcon, Languages, RotateCcw, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import type { QuestionSummaryOut } from "@/lib/lms/contentTypes";
import { btnSmall } from "./ui";

export function QuestionRow({
  courseId, q, busy, canEdit, onMove, onDelete, onRestore,
}: {
  courseId: string;
  q: QuestionSummaryOut;
  busy?: boolean;
  canEdit: boolean;
  onMove: (dir: "up" | "down") => void;
  onDelete: () => void;
  onRestore: () => void;
}) {
  const { lang, t } = useTranslation();
  const deleted = !!q.deleted_at;
  return (
    <li className={`flex items-start gap-3 px-4 py-3 ${deleted ? "bg-slate-50 opacity-75" : ""}`}>
      <span className="mt-1 w-8 flex-shrink-0 text-right text-xs font-mono text-slate-400" title={t("bank.questions.position")}>{q.q_num || q.position}</span>
      <div className="min-w-0 flex-1">
        <Link href={`/${lang}/courses/${courseId}/bank/q/${q.id}`} className="block hover:text-brand-700">
          {q.stem_excerpt ? <MathRenderer content={q.stem_excerpt} className="!text-sm line-clamp-2" /> : <span className="text-sm italic text-slate-400">{t("bank.questions.noStem")}</span>}
        </Link>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="rounded-full bg-brand-100 px-2 py-0.5 font-semibold text-brand-800">{t(`bank.types.${q.type}.name`)}</span>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 font-semibold text-slate-700">{t(`courses.languages.${q.language}`)}</span>
          {q.section && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">{q.section}</span>}
          {q.topic && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">{q.topic}</span>}
          {q.difficulty && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800">{t(`bank.difficulty.${q.difficulty}`)}</span>}
          {q.has_image && <ImageIcon className="h-3.5 w-3.5 text-slate-500" aria-label={t("bank.questions.hasImage")} />}
          {q.translation_group_id && <Languages className="h-3.5 w-3.5 text-slate-500" aria-label={t("bank.questions.hasTranslations")} />}
          {deleted && <span className="rounded-full bg-red-100 px-2 py-0.5 text-red-800">{t("bank.list.deletedBadge")}</span>}
        </div>
      </div>
      {canEdit && (
        <div className="flex flex-shrink-0 gap-1">
          {deleted ? (
            <button type="button" disabled={busy} className={btnSmall} onClick={onRestore} aria-label={t("bank.questions.restore")}>
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          ) : (
            <>
              <button type="button" disabled={busy} className={btnSmall} onClick={() => onMove("up")} aria-label={t("bank.questions.moveUp")}>
                <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
              <button type="button" disabled={busy} className={btnSmall} onClick={() => onMove("down")} aria-label={t("bank.questions.moveDown")}>
                <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
              <button type="button" disabled={busy} className={btnSmall} onClick={onDelete} aria-label={t("bank.questions.delete")}>
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </>
          )}
        </div>
      )}
    </li>
  );
}
