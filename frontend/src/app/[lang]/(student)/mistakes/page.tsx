"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import {
  BookX,
  Calendar,
  Award,
  CheckCircle2,
  XCircle,
  Clock,
  ArrowRight,
  FileText,
  Image as ImageIcon,
  MessageSquare,
  X,
  RefreshCw,
  Layers,
  ChevronRight,
} from "lucide-react";
import { getAuthHeader } from "@/lib/api";

interface DetailedReviewItem {
  questionId: string;
  section: string;
  stem: string;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  option_e?: string | null;
  image_url?: string | null;
  passage_text?: string | null;
  selectedOptionId?: string | null;
  correctOptionId: string;
  isCorrect: boolean;
  explanation?: string | null;
}

interface CompletedAttempt {
  attemptId: string;
  templateId: string;
  templateTitle?: string;
  language: string;
  completedAt?: string;
  scores?: {
    rawScore: number;
    scaledScore: number;
    percentile: number;
    isGoldenCertificate: boolean;
    sectionBreakdown?: Record<string, any>;
  };
  review?: DetailedReviewItem[];
}

export default function MistakesPortalPage() {
  const { lang, t } = useTranslation();

  const [attempts, setAttempts] = useState<CompletedAttempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAttemptId, setSelectedAttemptId] = useState<string | null>(null);
  const [activeReviewModalItem, setActiveReviewModalItem] = useState<DetailedReviewItem | null>(null);

  const fetchAttempts = async () => {
    try {
      setLoading(true);
      const authHeader = await getAuthHeader();
      const res = await fetch("/api/v1/mock-tests/attempts", {
        headers: authHeader,
      });
      if (res.ok) {
        const data = await res.json();
        setAttempts(data || []);
        if (data.length > 0 && !selectedAttemptId) {
          setSelectedAttemptId(data[0].attemptId);
        }
      }
    } catch (err) {
      console.error("Failed to load attempts:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAttempts();
  }, []);

  const selectedAttempt = attempts.find((a) => a.attemptId === selectedAttemptId) || attempts[0];
  const allMistakesInAttempt = (selectedAttempt?.review || []).filter((r) => !r.isCorrect);

  return (
    <div className="space-y-8 pb-12">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <span className="p-2 rounded-xl bg-rose-50 text-rose-600">
            <BookX className="w-6 h-6" />
          </span>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              {lang === "ky" ? "Каталар топтому жана талдоо" : "Тетрадь ошибок и разбор"}
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              {lang === "ky"
                ? "Тапшырылган сынактар боюнча топтолгон каталар. Ар бир суроону ачып, туура түшүндүрмөсүн көрүңүз."
                : "Ошибки сгруппированы по сданным экзаменационным сессиям с полным интерактивным разбором."}
            </p>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center p-12 bg-white rounded-3xl border border-slate-200">
          <RefreshCw className="w-8 h-8 animate-spin text-indigo-600 mb-2" />
          <span className="text-xs text-slate-400 font-medium">{t("common.loading")}</span>
        </div>
      ) : attempts.length === 0 ? (
        <div className="bg-white rounded-3xl border border-slate-200 p-12 text-center max-w-lg mx-auto space-y-4">
          <BookX className="w-12 h-12 text-slate-300 mx-auto" />
          <h3 className="font-bold text-slate-900 text-lg">
            {lang === "ky" ? "Азырынча тапшырылган сынактар жок" : "У вас пока нет завершенных тестов"}
          </h3>
          <p className="text-xs text-slate-500 leading-relaxed">
            {lang === "ky"
              ? "Сыноо тесттерин тапшыргандан кийин бардык туура эмес жоопторуңуз жана толук түшүндүрмөлөр бул жерде топтолот."
              : "После прохождения пробных тестов все допущенные ошибки и объяснения отобразятся в этом разделе."}
          </p>
          <div className="pt-2">
            <Link
              href={`/${lang}/mock-tests`}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold transition shadow-xs"
            >
              <span>{lang === "ky" ? "Сыноо тестин баштоо" : "Пройти пробный тест"}</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: List of Completed Attempts */}
          <div className="lg:col-span-4 space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 px-1">
              {lang === "ky" ? "Тапшырылган тесттер" : "Завершенные экзамены"}
            </h3>

            <div className="space-y-2">
              {attempts.map((att) => {
                const isSelected = att.attemptId === selectedAttempt?.attemptId;
                const mistakesCount = (att.review || []).filter((r) => !r.isCorrect).length;
                const dateStr = att.completedAt
                  ? new Date(att.completedAt).toLocaleDateString()
                  : "";

                return (
                  <button
                    key={att.attemptId}
                    onClick={() => setSelectedAttemptId(att.attemptId)}
                    className={`w-full p-4 rounded-2xl border text-left transition-all ${
                      isSelected
                        ? "bg-white border-indigo-600 shadow-md ring-2 ring-indigo-100"
                        : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/50"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-xs font-bold text-slate-900 line-clamp-1">
                        {att.templateTitle || (lang === "ky" ? "ОРТ Сыноо Тест" : "ОРТ Пробный тест")}
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                        {att.scores?.scaledScore || 60} {lang === "ky" ? "балл" : "б."}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-500">
                      <div className="flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5 text-slate-400" />
                        <span>{dateStr}</span>
                      </div>

                      <span
                        className={`font-semibold px-2 py-0.5 rounded-md ${
                          mistakesCount === 0
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-rose-50 text-rose-700 border border-rose-200"
                        }`}
                      >
                        {mistakesCount === 0
                          ? lang === "ky"
                            ? "Ката жок!"
                            : "Без ошибок!"
                          : `${mistakesCount} ${lang === "ky" ? "ката" : "ошибок"}`}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right Column: Mistakes List for Selected Attempt */}
          <div className="lg:col-span-8 space-y-4">
            <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs flex items-center justify-between">
              <div>
                <h3 className="font-bold text-slate-900 text-base">
                  {selectedAttempt?.templateTitle || "ОРТ Экзамен"}
                </h3>
                <span className="text-xs text-slate-500">
                  {allMistakesInAttempt.length}{" "}
                  {lang === "ky" ? "туура эмес жооп табылды" : "ошибок в этой попытке"}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-xl">
                  {selectedAttempt?.scores?.scaledScore || 60} {lang === "ky" ? "балл" : "баллов"}
                </span>
              </div>
            </div>

            {allMistakesInAttempt.length === 0 ? (
              <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center space-y-2">
                <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
                <h4 className="font-bold text-slate-900 text-base">
                  {lang === "ky" ? "Бул тестте каталар жок!" : "В этом тесте нет ошибок!"}
                </h4>
                <p className="text-xs text-slate-500">
                  {lang === "ky"
                    ? "Бардык суроолорго туура жооп бердиңиз. Азаматсыз!"
                    : "Вы ответили правильно на все вопросы раздела."}
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {allMistakesInAttempt.map((m, idx) => (
                  <div
                    key={m.questionId || idx}
                    onClick={() => setActiveReviewModalItem(m)}
                    className="bg-white rounded-2xl border border-slate-200 hover:border-indigo-400 p-5 shadow-xs hover:shadow-md transition-all cursor-pointer space-y-3 group"
                  >
                    <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                      <div className="flex items-center gap-2">
                        <span className="px-2.5 py-0.5 rounded-lg bg-slate-100 text-slate-700 font-bold text-[10px] uppercase">
                          {m.section}
                        </span>
                        <span className="text-xs text-rose-600 font-semibold flex items-center gap-1">
                          <XCircle className="w-3.5 h-3.5" />
                          <span>
                            {lang === "ky"
                              ? `Сиздин жооп: ${m.selectedOptionId || "Белгиленген эмес"}`
                              : `Ваш ответ: ${m.selectedOptionId || "Не выбран"}`}
                          </span>
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-xs text-emerald-600 font-semibold flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>
                            {lang === "ky"
                              ? `Туурасы: ${m.correctOptionId}`
                              : `Верно: ${m.correctOptionId}`}
                          </span>
                        </span>
                        <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-indigo-600 group-hover:translate-x-0.5 transition-all" />
                      </div>
                    </div>

                    {/* Question Stem preview */}
                    <div className="text-xs text-slate-800 line-clamp-2">
                      <MathRenderer content={m.stem} />
                    </div>

                    {/* Footer tags */}
                    <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                      <div className="flex items-center gap-2">
                        {m.passage_text && (
                          <span className="flex items-center gap-1 text-blue-600 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                            <FileText className="w-3 h-3" />
                            <span>Passage</span>
                          </span>
                        )}
                        {m.image_url && (
                          <span className="flex items-center gap-1 text-purple-600 bg-purple-50 px-2 py-0.5 rounded border border-purple-200">
                            <ImageIcon className="w-3 h-3" />
                            <span>Diagram</span>
                          </span>
                        )}
                        {m.explanation && (
                          <span className="flex items-center gap-1 text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                            <MessageSquare className="w-3 h-3" />
                            <span>Feedback</span>
                          </span>
                        )}
                      </div>

                      <span className="text-indigo-600 font-bold group-hover:underline">
                        {lang === "ky" ? "Толук талдоо →" : "Разбор вопроса →"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* INTERACTIVE QUESTION REVIEW MODAL */}
      {activeReviewModalItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-white w-full max-w-3xl rounded-3xl shadow-2xl border border-slate-200 overflow-hidden my-8 animate-in fade-in zoom-in-95">
            {/* Modal Top Bar */}
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50/80">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-1 rounded-lg bg-indigo-50 text-indigo-700 font-bold text-xs uppercase">
                  {activeReviewModalItem.section}
                </span>
                <span className="text-xs text-slate-500 font-medium">
                  {lang === "ky" ? "Катаны талдоо" : "Детальный разбор ошибки"}
                </span>
              </div>

              <button
                onClick={() => setActiveReviewModalItem(null)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded-lg transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-6 max-h-[80vh] overflow-y-auto">
              {/* If Diagram Image is attached */}
              {activeReviewModalItem.image_url && (
                <div className="bg-slate-50 p-4 rounded-2xl border border-slate-200 text-center">
                  <span className="text-[11px] font-bold text-purple-700 uppercase block mb-2">
                    {lang === "ky" ? "Суроонун сүрөтү / чертёжу" : "Чертеж к вопросу"}
                  </span>
                  <img
                    src={activeReviewModalItem.image_url}
                    alt="Diagram"
                    className="max-h-72 mx-auto object-contain rounded-lg border border-slate-200 shadow-xs"
                  />
                </div>
              )}

              {/* If Reading Passage is attached */}
              {activeReviewModalItem.passage_text && (
                <div className="bg-blue-50/40 p-6 rounded-2xl border border-blue-200 space-y-2 font-serif text-sm leading-relaxed text-slate-800">
                  <div className="text-xs font-sans font-bold text-blue-700 uppercase flex items-center gap-1.5 pb-2 border-b border-blue-100">
                    <FileText className="w-4 h-4" />
                    <span>{lang === "ky" ? "Окуу тексти" : "Материал для чтения"}</span>
                  </div>
                  <div className="whitespace-pre-line">
                    {activeReviewModalItem.passage_text}
                  </div>
                </div>
              )}

              {/* Question Stem */}
              <div className="bg-white p-5 rounded-2xl border border-slate-200 space-y-2">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
                  {lang === "ky" ? "Суроо:" : "Вопрос:"}
                </span>
                <div className="text-sm font-semibold text-slate-900 leading-relaxed">
                  <MathRenderer content={activeReviewModalItem.stem} />
                </div>
              </div>

              {/* Options A, B, C, D with Red (Wrong) & Green (Correct) Highlighting */}
              <div className="space-y-3">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
                  {lang === "ky" ? "Жооп варианттары:" : "Варианты ответов:"}
                </span>

                {[
                  { id: "A", text: activeReviewModalItem.option_a },
                  { id: "B", text: activeReviewModalItem.option_b },
                  { id: "C", text: activeReviewModalItem.option_c },
                  { id: "D", text: activeReviewModalItem.option_d },
                  ...(activeReviewModalItem.option_e
                    ? [{ id: "E", text: activeReviewModalItem.option_e }]
                    : []),
                ]
                  .filter((opt) => Boolean(opt.text))
                  .map((opt) => {
                    const isStudentWrong =
                      activeReviewModalItem.selectedOptionId === opt.id &&
                      opt.id !== activeReviewModalItem.correctOptionId;
                    const isCorrectAnswer = opt.id === activeReviewModalItem.correctOptionId;

                    let cardClass = "border-slate-200 bg-slate-50 text-slate-700";
                    let badge = null;

                    if (isStudentWrong) {
                      cardClass = "border-rose-400 bg-rose-50/90 text-rose-950 font-medium ring-2 ring-rose-200";
                      badge = (
                        <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-200 text-rose-800">
                          {lang === "ky" ? "Сиздин жообуңуз (Туура эмес)" : "Ваш ответ (Неверно)"}
                        </span>
                      );
                    } else if (isCorrectAnswer) {
                      cardClass = "border-emerald-500 bg-emerald-50/90 text-emerald-950 font-medium ring-2 ring-emerald-200";
                      badge = (
                        <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-200 text-emerald-900">
                          {lang === "ky" ? "Туура жооп ✓" : "Правильный ответ ✓"}
                        </span>
                      );
                    }

                    return (
                      <div
                        key={opt.id}
                        className={`p-4 rounded-xl border flex items-center justify-between text-xs transition-all ${cardClass}`}
                      >
                        <div className="flex items-center gap-3 flex-1">
                          <span
                            className={`w-7 h-7 rounded-lg flex items-center justify-center font-bold text-xs ${
                              isCorrectAnswer
                                ? "bg-emerald-600 text-white"
                                : isStudentWrong
                                ? "bg-rose-600 text-white"
                                : "bg-white border border-slate-200 text-slate-600"
                            }`}
                          >
                            {opt.id}
                          </span>
                          <div className="flex-1">
                            <MathRenderer content={opt.text} />
                          </div>
                        </div>

                        {badge && <div className="ml-3">{badge}</div>}
                      </div>
                    );
                  })}
              </div>

              {/* Full Problem-Solving Explanation */}
              {activeReviewModalItem.explanation && (
                <div className="p-5 rounded-2xl bg-indigo-50/70 border border-indigo-200 space-y-2 text-xs">
                  <div className="flex items-center gap-2 text-indigo-900 font-bold text-xs">
                    <MessageSquare className="w-4 h-4 text-indigo-600" />
                    <span>{lang === "ky" ? "Толук түшүндүрмө:" : "Подробное объяснение решения:"}</span>
                  </div>
                  <div className="text-slate-800 leading-relaxed">
                    <MathRenderer content={activeReviewModalItem.explanation} />
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3.5 border-t border-slate-200 bg-slate-50 flex items-center justify-end">
              <button
                onClick={() => setActiveReviewModalItem(null)}
                className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold transition shadow-xs"
              >
                {lang === "ky" ? "Жабуу" : "Закрыть"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
