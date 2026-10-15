"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import { ComparisonQuestionCard } from "@/components/exam/ComparisonQuestionCard";
import { Bookmark } from "lucide-react";

export { ComparisonQuestionCard };

interface QuestionCardProps {
  question: {
    id: string;
    section: string;
    topic: string;
    stem: string | { ky: string; ru: string };
    column_a?: string | null;
    column_b?: string | null;
    option_a?: string | null;
    option_b?: string | null;
    option_c?: string | null;
    option_d?: string | null;
    option_e?: string | null;
    options?: Array<{ id: string; text: string | { ky: string; ru: string } }>;
    passage_text?: string | null;
    image_url?: string | null;
  };
  questionNumber: number;
  totalQuestions: number;
  selectedOptionId?: string;
  isFlagged: boolean;
  onSelectOption: (optionId: string) => void;
  onToggleFlag: () => void;
}

export const QuestionCard: React.FC<QuestionCardProps> = ({
  question,
  questionNumber,
  totalQuestions,
  selectedOptionId,
  isFlagged,
  onSelectOption,
  onToggleFlag,
}) => {
  const { lang, t } = useTranslation();

  // Extract stem string
  const stemText =
    typeof question.stem === "object" && question.stem !== null
      ? lang === "ky"
        ? question.stem.ky
        : question.stem.ru
      : String(question.stem || "");

  // Quantitative comparison questions delegate directly to isolated ComparisonQuestionCard
  const isComparison = Boolean(question.column_a || question.column_b);
  if (isComparison) {
    return (
      <ComparisonQuestionCard
        question={question}
        questionNumber={questionNumber}
        totalQuestions={totalQuestions}
        selectedOptionId={selectedOptionId}
        isFlagged={isFlagged}
        onSelectOption={onSelectOption}
        onToggleFlag={onToggleFlag}
      />
    );
  }

  // Normalize options A, B, C, D, E for standard multiple choice
  let optionItems: Array<{ id: string; text: string }> = [];

  if (
    question.option_a ||
    question.option_b ||
    question.option_c ||
    question.option_d ||
    question.option_e
  ) {
    optionItems = [
      { id: "A", text: question.option_a || "" },
      { id: "B", text: question.option_b || "" },
      { id: "C", text: question.option_c || "" },
      { id: "D", text: question.option_d || "" },
      ...(question.option_e ? [{ id: "E", text: question.option_e }] : []),
    ].filter((o) => Boolean(o.text));
  } else if (Array.isArray(question.options)) {
    optionItems = question.options.map((opt) => ({
      id: opt.id,
      text:
        typeof opt.text === "object" && opt.text !== null
          ? lang === "ky"
            ? (opt.text as any).ky
            : (opt.text as any).ru
          : String(opt.text || ""),
    }));
  }

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-6">
      {/* Top Header of Question */}
      <div className="flex items-center justify-between border-b border-slate-100 pb-4">
        <div className="flex items-center gap-3">
          <span className="px-3 py-1 rounded-lg bg-indigo-50 text-indigo-700 font-sans font-bold text-xs uppercase tracking-wide">
            {t("exam.question")} {questionNumber} {t("exam.of")} {totalQuestions}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onToggleFlag}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-sans font-semibold border transition-all cursor-pointer ${
              isFlagged
                ? "bg-amber-100 border-amber-300 text-amber-800"
                : "bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100"
            }`}
          >
            <Bookmark className={`w-3.5 h-3.5 ${isFlagged ? "fill-amber-600 text-amber-600" : ""}`} />
            <span>{isFlagged ? t("exam.unflag") : t("exam.flagForReview")}</span>
          </button>
        </div>
      </div>

      {/* Main Standard Question Body */}
      <div className="min-h-[70px]">
        <MathRenderer content={stemText} className="font-serif text-gray-900 leading-relaxed text-base md:text-lg" />
      </div>

      {/* Universal Touch-Friendly Option Cards */}
      <div className="pt-1">
        {optionItems.map((opt) => {
          const isSelected = selectedOptionId === opt.id;

          return (
            <button
              key={opt.id}
              onClick={() => onSelectOption(opt.id)}
              className={`flex items-center w-full py-3 px-4 gap-3 mb-2 rounded-xl border text-left transition-all cursor-pointer ${
                isSelected
                  ? "border-indigo-600 bg-indigo-50/40 ring-1 ring-indigo-600 font-medium text-slate-900 shadow-xs"
                  : "border-slate-200 hover:border-indigo-300 bg-white text-slate-800 hover:bg-slate-50/50"
              }`}
            >
              <span
                className={`w-7 h-7 rounded-full flex items-center justify-center font-sans font-semibold text-sm shrink-0 transition-colors ${
                  isSelected
                    ? "bg-indigo-600 text-white shadow-xs"
                    : "bg-slate-100 border border-slate-200 text-slate-700"
                }`}
              >
                {opt.id}
              </span>
              <MathRenderer content={opt.text} className="flex-1 font-serif text-gray-900 leading-relaxed text-base" />
            </button>
          );
        })}
      </div>
    </div>
  );
};
