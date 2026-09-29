"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import { getAuthHeader } from "@/lib/api";
import {
  CheckCircle2,
  XCircle,
  BookOpen,
  HelpCircle,
  Sparkles,
  RotateCcw,
  ArrowRight,
  ArrowLeft,
  Award,
  FileText,
  Image as ImageIcon,
  Filter,
  Layers,
  RefreshCw,
  AlertCircle,
} from "lucide-react";

interface PracticeQuestionItem {
  id: string;
  section: string;
  topic: string;
  difficulty: string;
  language: string;
  stem: string;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  option_e?: string | null;
  correct_option: string;
  explanation?: string | null;
  image_url?: string | null;
  passage_text?: string | null;
  tags?: string[];
  exam_set_id?: string | null;
}

interface UserAnswerRecord {
  selectedOption: string;
  isCorrect: boolean;
  timeSpentSeconds: number;
}

interface PracticeSummary {
  attempt_id: string;
  section: string;
  total_questions: number;
  correct_count: number;
  accuracy_percentage: number;
  message: string;
}

export default function PracticePage() {
  const { lang, t } = useTranslation();

  const sections = [
    { id: "math_1", name: lang === "ky" ? "1-Бөлүм: Математика I" : "Раздел 1: Математика I" },
    { id: "math_2", name: lang === "ky" ? "2-Бөлүм: Математика II" : "Раздел 2: Математика II" },
    { id: "reading", name: lang === "ky" ? "3-Бөлүм: Окуу жана түшүнүү" : "Раздел 3: Чтение и понимание" },
    { id: "analogies", name: lang === "ky" ? "4-Бөлүм: Аналогиялар" : "Раздел 4: Аналогии" },
    { id: "grammar", name: lang === "ky" ? "5-Бөлүм: Практикалык грамматика" : "Раздел 5: Практическая грамматика" },
  ];

  const [activeSection, setActiveSection] = useState("math_1");
  const [topics, setTopics] = useState<string[]>([]);
  const [selectedTopic, setSelectedTopic] = useState<string>("");
  const [loadingTopics, setLoadingTopics] = useState(false);

  const [questions, setQuestions] = useState<PracticeQuestionItem[]>([]);
  const [loadingQuestions, setLoadingQuestions] = useState(true);
  const [errorQuestions, setErrorQuestions] = useState<string | null>(null);

  const [userAnswers, setUserAnswers] = useState<Record<string, UserAnswerRecord>>({});
  const [questionStartTimes, setQuestionStartTimes] = useState<Record<string, number>>({});

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [summary, setSummary] = useState<PracticeSummary | null>(null);

  // 1. Fetch available topics for current section
  const fetchTopics = useCallback(async (sec: string) => {
    try {
      setLoadingTopics(true);
      const authHeader = await getAuthHeader();
      const res = await fetch(`/api/v1/practice/topics?section=${encodeURIComponent(sec)}&lang=${lang}`, {
        headers: authHeader,
      });
      if (res.ok) {
        const data = await res.json();
        setTopics(Array.isArray(data) ? data : []);
      }
    } catch (e) {
      console.warn("Failed to fetch topics:", e);
    } finally {
      setLoadingTopics(false);
    }
  }, [lang]);

  // 2. Fetch 10 questions for current section & topic
  const fetchQuestions = useCallback(async (sec: string, top: string) => {
    try {
      setLoadingQuestions(true);
      setErrorQuestions(null);
      setUserAnswers({});
      setSummary(null);

      const authHeader = await getAuthHeader();
      const topicQuery = top ? `&topic=${encodeURIComponent(top)}` : "";
      const res = await fetch(`/api/v1/practice/questions?section=${encodeURIComponent(sec)}${topicQuery}&lang=${lang}&limit=10`, {
        headers: authHeader,
      });

      if (!res.ok) {
        throw new Error(lang === "ky" ? "Суроолорду жүктөөдө ката кетти" : "Ошибка при загрузке вопросов");
      }

      const data = await res.json();
      if (Array.isArray(data)) {
        setQuestions(data);
        const now = Date.now();
        const startTimes: Record<string, number> = {};
        data.forEach((q) => {
          startTimes[q.id] = now;
        });
        setQuestionStartTimes(startTimes);
      } else {
        setQuestions([]);
      }
    } catch (e: any) {
      console.error("Failed to load questions:", e);
      setErrorQuestions(e.message || "Failed to load questions");
    } finally {
      setLoadingQuestions(false);
    }
  }, [lang]);

  // When active section changes, refresh topics and load questions
  useEffect(() => {
    fetchTopics(activeSection);
    setSelectedTopic("");
    fetchQuestions(activeSection, "");
  }, [activeSection, fetchTopics, fetchQuestions]);

  // When user selects a specific topic from dropdown
  const handleTopicChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newTopic = e.target.value;
    setSelectedTopic(newTopic);
    fetchQuestions(activeSection, newTopic);
  };

  // Instant option evaluation
  const handleSelectOption = (question: PracticeQuestionItem, optionKey: string) => {
    if (userAnswers[question.id]) return; // Question is already locked

    const normalizedChoice = optionKey.toUpperCase().trim();
    const normalizedCorrect = question.correct_option.toUpperCase().trim();
    const isCorrect = normalizedChoice === normalizedCorrect;

    const startTime = questionStartTimes[question.id] || Date.now();
    const timeSpent = Math.max(1, Math.round((Date.now() - startTime) / 1000));

    setUserAnswers((prev) => ({
      ...prev,
      [question.id]: {
        selectedOption: normalizedChoice,
        isCorrect,
        timeSpentSeconds: timeSpent,
      },
    }));
  };

  // Check if all questions are answered
  const answeredCount = Object.keys(userAnswers).length;
  const totalQuestions = questions.length;
  const isSetComplete = totalQuestions > 0 && answeredCount >= totalQuestions;

  // Submit completed practice set to backend
  const handleFinishPracticeSet = async () => {
    if (!isSetComplete || isSubmitting) return;

    try {
      setIsSubmitting(true);
      const authHeader = await getAuthHeader();

      const answersPayload = questions.map((q) => {
        const ans = userAnswers[q.id];
        return {
          question_id: q.id,
          selected_option: ans?.selectedOption || "A",
          is_correct: ans?.isCorrect ?? false,
          time_spent_seconds: ans?.timeSpentSeconds || 0,
        };
      });

      const payload = {
        section: activeSection,
        topic: selectedTopic || null,
        language: lang,
        answers: answersPayload,
      };

      const res = await fetch("/api/v1/practice/submit-set", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeader,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error("Failed to submit practice set");
      }

      const summaryData = await res.json();
      setSummary(summaryData);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e: any) {
      alert(e.message || "Failed to submit set");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStartNewSet = () => {
    fetchQuestions(activeSection, selectedTopic);
  };

  const activeSectionObj = sections.find((s) => s.id === activeSection) || sections[0];

  return (
    <div className="space-y-8 pb-16 max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2.5">
          <span className="p-2 rounded-2xl bg-indigo-50 text-indigo-600 border border-indigo-100 shadow-xs">
            <BookOpen className="w-5 h-5" />
          </span>
          <div>
            <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">
              {lang === "ky" ? "Бөлүмдөр боюнча машыгуу" : "Тематическая практика"}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {lang === "ky"
                ? "Машыгуу базасынан 10 суроодон турган топтомдор. Дароо жоопторду текшерүү жана кадамдык түшүндүрмөлөр."
                : "Формирующая тренировка сетами по 10 вопросов с моментальной проверкой и пошаговыми подсказками."}
            </p>
          </div>
        </div>
      </div>

      {/* Section Tabs */}
      <div className="bg-slate-100/80 p-1.5 rounded-2xl border border-slate-200/80 flex gap-1.5 overflow-x-auto shadow-2xs">
        {sections.map((sec) => {
          const isActive = activeSection === sec.id;
          return (
            <button
              key={sec.id}
              onClick={() => setActiveSection(sec.id)}
              className={`px-4 py-2.5 rounded-xl text-xs font-bold whitespace-nowrap transition-all cursor-pointer ${
                isActive
                  ? "bg-white text-indigo-600 shadow-sm border border-slate-200/60"
                  : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/50"
              }`}
            >
              {sec.name}
            </button>
          );
        })}
      </div>

      {/* Controls: Topic Filter Dropdown & Progress */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-xs flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        {/* Topic dropdown */}
        <div className="flex items-center gap-2.5 flex-1 max-w-md">
          <Filter className="w-4 h-4 text-slate-400 shrink-0" />
          <div className="flex-1">
            <select
              value={selectedTopic}
              onChange={handleTopicChange}
              disabled={loadingTopics || loadingQuestions}
              className="w-full text-xs font-semibold text-slate-700 bg-slate-50 hover:bg-slate-100/80 border border-slate-200 rounded-xl px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition cursor-pointer"
            >
              <option value="">
                {lang === "ky" ? "Бардык темалар (Аралаш)" : "Все темы (Случайная подборка)"}
              </option>
              {topics.map((top) => (
                <option key={top} value={top}>
                  {top.replace(/_/g, " ").toUpperCase()}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Refresh button */}
        <button
          onClick={handleStartNewSet}
          disabled={loadingQuestions}
          className="inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition cursor-pointer shrink-0"
        >
          <RotateCcw className={`w-3.5 h-3.5 ${loadingQuestions ? "animate-spin" : ""}`} />
          <span>{lang === "ky" ? "Жаңы 10 суроо" : "Новый сет из 10"}</span>
        </button>
      </div>

      {/* MINI-SUMMARY SCREEN (Rendered upon completing the 10 questions) */}
      {summary ? (
        <div className="bg-white rounded-3xl border border-slate-200/80 p-8 sm:p-10 shadow-sm text-center space-y-6 animate-in fade-in zoom-in-95 duration-200">
          <div className="w-20 h-20 rounded-3xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mx-auto shadow-xs">
            <Award className="w-10 h-10" />
          </div>

          <div className="space-y-2">
            <h3 className="text-2xl font-extrabold text-slate-900">
              {lang === "ky" ? "Машыгуу ийгиликтүү аяктады!" : "Тренировочный сет завершен!"}
            </h3>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              {summary.message}
            </p>
          </div>

          {/* Score card */}
          <div className="p-6 bg-slate-50 rounded-2xl border border-slate-100 max-w-sm mx-auto space-y-3">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
              {lang === "ky" ? "Жалпы көрсөткүч" : "Итоговый счет"}
            </span>
            <div className="flex items-baseline justify-center gap-2">
              <span className="text-5xl font-extrabold text-indigo-600">
                {summary.correct_count}
              </span>
              <span className="text-2xl font-bold text-slate-400">
                / {summary.total_questions}
              </span>
            </div>
            <div className="inline-block px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
              {summary.accuracy_percentage}% {lang === "ky" ? "тактык" : "точность"}
            </div>
          </div>

          <p className="text-xs text-emerald-600 font-semibold max-w-sm mx-auto">
            {lang === "ky"
              ? "✓ Жыйынтык Сиздин прогресс баракчаңыздагы бөлүмдү өздөштүрүү шкаласына кошулду!"
              : "✓ Результаты успешно добавлены в шкалу освоения разделов на странице прогресса!"}
          </p>

          <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
            <button
              onClick={handleStartNewSet}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold transition shadow-xs cursor-pointer"
            >
              <RotateCcw className="w-4 h-4" />
              <span>{lang === "ky" ? "Кийинки 10 суроону баштоо" : "Начать новый сет (10 вопросов)"}</span>
            </button>

            <Link
              href={`/${lang}/progress`}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition"
            >
              <span>{lang === "ky" ? "Прогрессти көрүү" : "Моя статистика"}</span>
              <ArrowRight className="w-4 h-4" />
            </Link>

            <Link
              href={`/${lang}/dashboard`}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition"
            >
              <span>{lang === "ky" ? "Башкы бетке кайтуу" : "Вернуться на главную"}</span>
            </Link>
          </div>
        </div>
      ) : (
        <>
          {/* Progress Banner */}
          {!loadingQuestions && questions.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-2xs space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold">
                <span className="text-slate-600">
                  {lang === "ky" ? "Топтомдун жүрүшү:" : "Прогресс сета:"}
                </span>
                <span className="text-indigo-600 font-bold">
                  {answeredCount} / {totalQuestions}{" "}
                  {lang === "ky" ? "жооп берилди" : "отвечено"}
                </span>
              </div>
              <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-indigo-600 rounded-full transition-all duration-300"
                  style={{ width: `${(answeredCount / totalQuestions) * 100}%` }}
                />
              </div>
            </div>
          )}

          {/* Loading state */}
          {loadingQuestions && (
            <div className="min-h-[40vh] flex flex-col items-center justify-center gap-3 text-slate-400">
              <RefreshCw className="w-8 h-8 animate-spin text-indigo-600" />
              <span className="text-xs font-semibold">
                {lang === "ky" ? "Суроолор тандалып жатат..." : "Формируем персональный сет..."}
              </span>
            </div>
          )}

          {/* Error state */}
          {errorQuestions && !loadingQuestions && (
            <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 text-center space-y-3">
              <AlertCircle className="w-8 h-8 text-rose-600 mx-auto" />
              <p className="text-xs font-semibold text-rose-800">{errorQuestions}</p>
              <button
                onClick={handleStartNewSet}
                className="px-4 py-2 bg-rose-600 text-white rounded-xl text-xs font-bold hover:bg-rose-700 transition"
              >
                {lang === "ky" ? "Кайра аракет кылуу" : "Попробовать снова"}
              </button>
            </div>
          )}

          {/* Empty state */}
          {!loadingQuestions && !errorQuestions && questions.length === 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-10 text-center space-y-4">
              <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
                <Layers className="w-6 h-6" />
              </div>
              <h4 className="font-bold text-slate-900 text-sm">
                {lang === "ky" ? "Суроолор табылган жок" : "Вопросы не найдены"}
              </h4>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                {lang === "ky"
                  ? "Бул бөлүм же тема боюнча суроолор базасы жаңыланып жатат. Башка теманы тандап көрүңүз."
                  : "Для выбранного раздела или темы вопросы пока формируются. Попробуйте выбрать другую тему."}
              </p>
            </div>
          )}

          {/* QUESTION CARDS FEED (Formative UI with instant feedback) */}
          {!loadingQuestions && questions.length > 0 && (
            <div className="space-y-6">
              {questions.map((q, idx) => {
                const answerRecord = userAnswers[q.id];
                const isAnswered = Boolean(answerRecord);
                const isCorrect = answerRecord?.isCorrect;
                const selectedOption = answerRecord?.selectedOption;
                const correctOption = q.correct_option.toUpperCase().trim();

                const optionKeys = ["A", "B", "C", "D"];
                if (q.option_e && q.option_e.trim()) {
                  optionKeys.push("E");
                }

                return (
                  <div
                    key={q.id}
                    id={`question-card-${q.id}`}
                    className={`bg-white rounded-3xl border transition-all duration-200 p-6 sm:p-7 shadow-xs space-y-5 ${
                      isAnswered
                        ? isCorrect
                          ? "border-emerald-200 ring-1 ring-emerald-100"
                          : "border-rose-200 ring-1 ring-rose-100"
                        : "border-slate-200/90 hover:border-slate-300"
                    }`}
                  >
                    {/* Card Header */}
                    <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-3">
                      <div className="flex items-center gap-2">
                        <span className="px-2.5 py-1 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-700 text-[11px] font-extrabold tracking-wide uppercase">
                          {lang === "ky" ? `Суроо #${idx + 1}` : `Вопрос #${idx + 1}`}
                        </span>
                        {q.topic && (
                          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider truncate max-w-[200px]">
                            {q.topic.replace(/_/g, " ")}
                          </span>
                        )}
                      </div>

                      {isAnswered && (
                        <div className="flex items-center gap-1.5 animate-in fade-in duration-200">
                          {isCorrect ? (
                            <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-600 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
                              <CheckCircle2 className="w-3.5 h-3.5" />
                              <span>{lang === "ky" ? "Туура!" : "Правильно!"}</span>
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs font-bold text-rose-600 bg-rose-50 px-2.5 py-1 rounded-full border border-rose-200">
                              <XCircle className="w-3.5 h-3.5" />
                              <span>{lang === "ky" ? "Ката" : "Неверно"}</span>
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Passage text if provided */}
                    {q.passage_text && (
                      <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-2xl text-xs text-slate-700 leading-relaxed max-h-48 overflow-y-auto">
                        <div className="flex items-center gap-1.5 text-[11px] font-bold text-slate-400 uppercase mb-2">
                          <FileText className="w-3.5 h-3.5" />
                          <span>{lang === "ky" ? "Окуу тексти" : "Текст для чтения"}</span>
                        </div>
                        <MathRenderer content={q.passage_text} />
                      </div>
                    )}

                    {/* Image / diagram if provided */}
                    {q.image_url && (
                      <div className="flex items-center justify-center p-3 bg-slate-50 border border-slate-200/70 rounded-2xl">
                        <img
                          src={q.image_url}
                          alt="Question diagram"
                          className="max-h-64 max-w-full object-contain rounded-xl"
                        />
                      </div>
                    )}

                    {/* Question Stem */}
                    <div className="text-sm sm:text-base font-semibold text-slate-900 leading-relaxed">
                      <MathRenderer content={q.stem} />
                    </div>

                    {/* Options (Instant click evaluation) */}
                    <div className="grid grid-cols-1 gap-2.5 pt-1">
                      {optionKeys.map((key) => {
                        let optText = "";
                        if (key === "A") optText = q.option_a;
                        else if (key === "B") optText = q.option_b;
                        else if (key === "C") optText = q.option_c;
                        else if (key === "D") optText = q.option_d;
                        else if (key === "E") optText = q.option_e || "";

                        const isThisSelected = selectedOption === key;
                        const isThisCorrect = correctOption === key;

                        let buttonClasses = "border-slate-200 bg-slate-50/50 hover:bg-slate-100 hover:border-indigo-300 text-slate-800";
                        let badgeClasses = "bg-white border-slate-200 text-slate-700";

                        if (isAnswered) {
                          if (isThisSelected && isThisCorrect) {
                            // Student selected correct option
                            buttonClasses = "border-emerald-500 bg-emerald-50 text-emerald-950 font-bold shadow-xs";
                            badgeClasses = "bg-emerald-600 border-emerald-600 text-white";
                          } else if (isThisSelected && !isThisCorrect) {
                            // Student selected wrong option
                            buttonClasses = "border-rose-500 bg-rose-50 text-rose-950 font-bold shadow-xs";
                            badgeClasses = "bg-rose-600 border-rose-600 text-white";
                          } else if (isThisCorrect) {
                            // Highlight the actual correct option in green
                            buttonClasses = "border-emerald-400 bg-emerald-50/60 text-emerald-950 font-bold";
                            badgeClasses = "bg-emerald-600 border-emerald-600 text-white";
                          } else {
                            // Other unselected options dimmed
                            buttonClasses = "border-slate-100 bg-slate-50/30 text-slate-400 opacity-60";
                            badgeClasses = "bg-slate-100 border-slate-200 text-slate-400";
                          }
                        }

                        return (
                          <button
                            key={key}
                            onClick={() => handleSelectOption(q, key)}
                            disabled={isAnswered}
                            className={`w-full flex items-center gap-3 p-3.5 rounded-2xl border text-left text-xs sm:text-sm transition-all duration-150 ${buttonClasses} ${
                              !isAnswered ? "cursor-pointer" : "cursor-default"
                            }`}
                          >
                            <span
                              className={`w-7 h-7 rounded-xl border flex items-center justify-center font-extrabold text-xs shrink-0 transition-colors ${badgeClasses}`}
                            >
                              {key}
                            </span>
                            <div className="flex-1 overflow-x-auto">
                              <MathRenderer content={optText} />
                            </div>

                            {/* Status indicator on option */}
                            {isAnswered && (
                              <div className="shrink-0">
                                {isThisSelected && isThisCorrect && (
                                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                                )}
                                {isThisSelected && !isThisCorrect && (
                                  <XCircle className="w-4 h-4 text-rose-600" />
                                )}
                                {!isThisSelected && isThisCorrect && (
                                  <span className="text-[11px] font-bold text-emerald-700 bg-emerald-100/80 px-2 py-0.5 rounded-md">
                                    {lang === "ky" ? "Туура жооп" : "Правильный ответ"}
                                  </span>
                                )}
                              </div>
                            )}
                          </button>
                        );
                      })}
                    </div>

                    {/* THE EXPLANATION REVEAL (Drops down dynamically upon option click) */}
                    {isAnswered && (
                      <div className="pt-2 animate-in fade-in slide-in-from-top-2 duration-300">
                        <div className="p-4 sm:p-5 rounded-2xl bg-indigo-50/70 border border-indigo-200/80 text-xs sm:text-sm text-slate-800 space-y-2">
                          <div className="flex items-center gap-1.5 font-extrabold text-indigo-950 text-xs">
                            <Sparkles className="w-4 h-4 text-indigo-600" />
                            <span>{lang === "ky" ? "Чыгаруу жолу жана түшүндүрмө:" : "Пошаговое объяснение:"}</span>
                          </div>
                          <div className="text-slate-700 leading-relaxed">
                            {q.explanation ? (
                              <MathRenderer content={q.explanation} />
                            ) : (
                              <span className="text-slate-400 italic">
                                {lang === "ky"
                                  ? "Бул суроого түшүндүрмө кошулган эмес."
                                  : "Объяснение для данного вопроса пока не добавлено."}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Bottom Finish Practice Set Sticky / Prominent Bar */}
              <div className="sticky bottom-6 z-20 bg-white/95 backdrop-blur-md rounded-2xl border border-slate-200 p-4 shadow-lg flex flex-col sm:flex-row items-center justify-between gap-3">
                <div className="text-xs text-slate-600">
                  {isSetComplete ? (
                    <span className="text-emerald-700 font-bold flex items-center gap-1.5">
                      <CheckCircle2 className="w-4 h-4" />
                      {lang === "ky"
                        ? "Бардык 10 суроо аткарылды! Жыйынтыкты сактоого даяр."
                        : "Все 10 вопросов завершены! Готово к подведению итогов."}
                    </span>
                  ) : (
                    <span>
                      {lang === "ky"
                        ? `Машыгууну аяктоо үчүн бардык суроолорго жооп бериңиз (${answeredCount} / ${totalQuestions})`
                        : `Ответьте на все вопросы для завершения сета (${answeredCount} / ${totalQuestions})`}
                    </span>
                  )}
                </div>

                <button
                  onClick={handleFinishPracticeSet}
                  disabled={!isSetComplete || isSubmitting}
                  className={`w-full sm:w-auto px-7 py-3 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition shadow-xs ${
                    isSetComplete && !isSubmitting
                      ? "bg-indigo-600 hover:bg-indigo-700 text-white cursor-pointer"
                      : "bg-slate-200 text-slate-400 cursor-not-allowed"
                  }`}
                >
                  {isSubmitting ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <Award className="w-4 h-4" />
                  )}
                  <span>
                    {lang === "ky" ? "Машыгууну аяктоо" : "Завершить тренировку"}
                  </span>
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
