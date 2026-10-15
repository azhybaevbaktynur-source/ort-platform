"use client";

import React, { useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import { Bookmark, EyeOff } from "lucide-react";

export interface ComparisonQuestionCardProps {
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

export const ComparisonQuestionCard: React.FC<ComparisonQuestionCardProps> = ({
  question,
  questionNumber,
  totalQuestions,
  selectedOptionId,
  isFlagged,
  onSelectOption,
  onToggleFlag,
}) => {
  const { lang, t } = useTranslation();

  // State to track visually eliminated/struck-through options for this question
  const [eliminatedOptions, setEliminatedOptions] = useState<Record<string, boolean>>({});

  // Extract clean stem text (condition/context)
  const stemText =
    typeof question.stem === "object" && question.stem !== null
      ? lang === "ky"
        ? question.stem.ky
        : question.stem.ru
      : String(question.stem || "").trim();

  // Standard ORT fallback options if not provided
  const defaultOptionTexts: Record<string, { ky: string; ru: string }> = {
    A: {
      ky: "КОЛОНКА А чоңураак",
      ru: "Значение в Колонке А больше",
    },
    B: {
      ky: "КОЛОНКА Б чоңураак",
      ru: "Значение в Колонке Б больше",
    },
    C: {
      ky: "Эки чоңдук барабар",
      ru: "Величины равны",
    },
    D: {
      ky: "Маалымат жетишсиз",
      ru: "Недостаточно информации для определения",
    },
  };

  // Build options list
  let optionItems: Array<{ id: string; text: string }> = [];

  if (
    question.option_a ||
    question.option_b ||
    question.option_c ||
    question.option_d ||
    question.option_e
  ) {
    optionItems = [
      { id: "A", text: question.option_a || (lang === "ky" ? defaultOptionTexts.A.ky : defaultOptionTexts.A.ru) },
      { id: "B", text: question.option_b || (lang === "ky" ? defaultOptionTexts.B.ky : defaultOptionTexts.B.ru) },
      { id: "C", text: question.option_c || (lang === "ky" ? defaultOptionTexts.C.ky : defaultOptionTexts.C.ru) },
      { id: "D", text: question.option_d || (lang === "ky" ? defaultOptionTexts.D.ky : defaultOptionTexts.D.ru) },
      ...(question.option_e ? [{ id: "E", text: question.option_e }] : []),
    ];
  } else if (Array.isArray(question.options) && question.options.length > 0) {
    optionItems = question.options.map((opt) => ({
      id: opt.id,
      text:
        typeof opt.text === "object" && opt.text !== null
          ? lang === "ky"
            ? (opt.text as any).ky
            : (opt.text as any).ru
          : String(opt.text || ""),
    }));
  } else {
    // Default 4 standard ORT quantitative comparison options
    optionItems = ["A", "B", "C", "D"].map((id) => ({
      id,
      text: lang === "ky" ? defaultOptionTexts[id].ky : defaultOptionTexts[id].ru,
    }));
  }

  const toggleEliminate = (optId: string) => {
    setEliminatedOptions((prev) => ({
      ...prev,
      [optId]: !prev[optId],
    }));
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 md:p-8 w-full max-w-4xl mx-auto space-y-6">
      {/* Top Header */}
      <div className="flex items-center justify-between border-b border-slate-100 pb-4">
        <div className="flex items-center gap-3">
          <span className="px-3 py-1 rounded-lg bg-indigo-50 text-indigo-700 font-sans font-bold text-xs uppercase tracking-wide">
            {t("exam.question")} {questionNumber} {t("exam.of")} {totalQuestions}
          </span>
        </div>

        <button
          type="button"
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

      {/* Stem text: rendered on its own line above comparison boxes */}
      {stemText ? (
        <div className="bg-slate-50/80 rounded-xl p-4 border border-slate-200/80 font-serif text-gray-900 leading-relaxed text-base">
          <MathRenderer content={stemText} />
        </div>
      ) : null}

      {/* Side-by-side comparison grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        {/* Column A */}
        <div className="bg-slate-50/60 rounded-2xl border-2 border-slate-200 p-4 md:p-6 flex flex-col justify-between text-center shadow-xs transition hover:border-slate-300">
          <div className="inline-block bg-gray-100 text-gray-500 font-bold text-xs tracking-widest uppercase px-3 py-1 rounded-md mx-auto mb-3">
            {lang === "ky" ? "КОЛОНКА А" : "КОЛОНКА А"}
          </div>
          <div className="py-2 flex items-center justify-center min-h-[60px] text-xl font-semibold text-gray-900">
            <MathRenderer content={question.column_a || "—"} />
          </div>
        </div>

        {/* Column B */}
        <div className="bg-slate-50/60 rounded-2xl border-2 border-slate-200 p-4 md:p-6 flex flex-col justify-between text-center shadow-xs transition hover:border-slate-300">
          <div className="inline-block bg-gray-100 text-gray-500 font-bold text-xs tracking-widest uppercase px-3 py-1 rounded-md mx-auto mb-3">
            {lang === "ky" ? "КОЛОНКА Б" : "КОЛОНКА Б"}
          </div>
          <div className="py-2 flex items-center justify-center min-h-[60px] text-xl font-semibold text-gray-900">
            <MathRenderer content={question.column_b || "—"} />
          </div>
        </div>
      </div>

      {/* Options list: A, B, C, D in compact list */}
      <div className="flex flex-col pt-1">
        {optionItems.map((opt) => {
          const isSelected = selectedOptionId === opt.id;
          const isEliminated = Boolean(eliminatedOptions[opt.id]);

          return (
            <div
              key={opt.id}
              onClick={() => {
                if (!isEliminated) {
                  onSelectOption(opt.id);
                } else {
                  // If clicked while eliminated, un-eliminate and select
                  toggleEliminate(opt.id);
                  onSelectOption(opt.id);
                }
              }}
              className={`w-full flex items-center justify-between border rounded-xl py-3 px-4 gap-3 mb-2 cursor-pointer transition-colors ${
                isEliminated
                  ? "opacity-40 line-through bg-slate-50 border-slate-200 text-slate-400"
                  : isSelected
                  ? "ring-2 ring-indigo-500 bg-indigo-50/50 border-indigo-600 font-medium text-slate-900 shadow-xs"
                  : "border-slate-200 hover:border-indigo-300 bg-white text-slate-800 hover:bg-slate-50/50"
              }`}
            >
              {/* Left Side: Letter circle badge + text */}
              <div className="flex items-center gap-3 flex-1 min-w-0 pr-3">
                <span
                  className={`w-7 h-7 rounded-full flex items-center justify-center font-sans font-semibold text-sm shrink-0 transition-colors ${
                    isEliminated
                      ? "bg-slate-200 text-slate-500"
                      : isSelected
                      ? "bg-indigo-600 text-white shadow-xs"
                      : "bg-slate-100 border border-slate-200 text-slate-700"
                  }`}
                >
                  {opt.id}
                </span>
                <div className={`flex-1 font-serif text-gray-900 leading-relaxed text-base ${isEliminated ? "line-through text-slate-400" : ""}`}>
                  <MathRenderer content={opt.text} />
                </div>
              </div>

              {/* Right Side: Eye-slash icon button representing visual elimination/crossing out */}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleEliminate(opt.id);
                }}
                className={`p-1.5 rounded-lg transition-colors cursor-pointer shrink-0 ${
                  isEliminated
                    ? "text-slate-700 bg-slate-200/80 hover:bg-slate-300"
                    : "text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                }`}
                title={
                  isEliminated
                    ? (lang === "ky" ? "Вариантты кайтаруу" : "Восстановить вариант")
                    : (lang === "ky" ? "Вариантты чийип салуу" : "Исключить вариант (зачеркнуть)")
                }
                aria-label={lang === "ky" ? "Вариантты чийип салуу" : "Исключить вариант"}
              >
                <EyeOff className={`w-3.5 h-3.5 ${isEliminated ? "stroke-[2.5]" : ""}`} />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};

