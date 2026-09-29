"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { Bookmark } from "lucide-react";

interface QuestionPaletteProps {
  totalQuestions: number;
  currentIndex: number;
  onSelectIndex: (index: number) => void;
  answers: Record<string, { selectedOptionId?: string; flagged?: boolean }>;
  questionIds: string[];
}

export const QuestionPalette: React.FC<QuestionPaletteProps> = ({
  totalQuestions,
  currentIndex,
  onSelectIndex,
  answers,
  questionIds,
}) => {
  const { lang, t } = useTranslation();

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs flex flex-col h-full">
      <h3 className="font-bold text-slate-900 text-sm mb-3">
        {lang === "ky" ? "Суроолор таблицасы" : "Навигация по вопросам"}
      </h3>

      {/* Question Number Matrix */}
      <div className="grid grid-cols-5 gap-2 overflow-y-auto max-h-72 p-1">
        {questionIds.map((qId, idx) => {
          const isCurrent = currentIndex === idx;
          const ans = answers[qId];
          const isAnswered = ans && !!ans.selectedOptionId;
          const isFlagged = ans && !!ans.flagged;

          let btnClass = "border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100";

          if (isCurrent) {
            btnClass = "border-brand-600 bg-brand-600 text-white font-bold ring-2 ring-brand-300";
          } else if (isFlagged) {
            btnClass = "border-amber-400 bg-amber-100 text-amber-900 font-bold";
          } else if (isAnswered) {
            btnClass = "border-emerald-400 bg-emerald-50 text-emerald-800 font-semibold";
          }

          return (
            <button
              key={qId}
              onClick={() => onSelectIndex(idx)}
              className={`relative h-10 rounded-xl border text-xs flex items-center justify-center transition-all ${btnClass}`}
            >
              {idx + 1}
              {isFlagged && !isCurrent && (
                <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-amber-500" />
              )}
            </button>
          );
        })}
      </div>

      {/* Legend */}
      <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-2 gap-2 text-[11px] text-slate-600">
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-md bg-emerald-100 border border-emerald-400" />
          <span>{t("exam.answered")}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-md bg-amber-100 border border-amber-400" />
          <span>{t("exam.flagged")}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-md bg-slate-100 border border-slate-200" />
          <span>{t("exam.unanswered")}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-md bg-brand-600 border border-brand-600" />
          <span>{lang === "ky" ? "Учурдагы" : "Текущий"}</span>
        </div>
      </div>
    </div>
  );
};

