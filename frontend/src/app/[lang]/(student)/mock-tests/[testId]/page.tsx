"use client";

import React, { useState, useEffect, useMemo, useCallback, Suspense } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { ExamTimer } from "@/components/exam/ExamTimer";
import { QuestionPalette } from "@/components/exam/QuestionPalette";
import { QuestionCard } from "@/components/exam/QuestionCard";
import { MathRenderer } from "@/components/math/MathRenderer";
import {
  ArrowLeft,
  ArrowRight,
  Send,
  AlertTriangle,
  AlertCircle,
  KeyRound,
  CheckCircle2,
  Layers,
  Clock,
  FileText,
  Image as ImageIcon,
  Sparkles,
  RefreshCw,
  Award,
} from "lucide-react";
import { getAuthHeader } from "@/lib/api";

interface QuestionItem {
  id: string;
  section: string;
  topic: string;
  stem: string;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  option_e?: string | null;
  passage_text?: string | null;
  image_url?: string | null;
}

interface SectionItem {
  section: string;
  questionCount: number;
  timeLimitMinutes: number;
}

interface SectionScore {
  section: string;
  rawScore: number;
  totalQuestions: number;
  scaledScore: number;
  accuracyPercentage: number;
}

interface MockTestFinalResult {
  attemptId: string;
  totalRawScore: number;
  maxRawScore: number;
  totalScaledScore: number;
  percentile: number;
  isGoldenCertificate: boolean;
  sectionScores: Record<string, SectionScore>;
}

const STRICT_SECTION_ORDER = [
  "math_1",
  "math_2",
  "reading",
  "analogies",
  "grammar",
  "chemistry",
  "biology",
  "physics",
  "history",
  "english",
];

const DEFAULT_SECTIONS: SectionItem[] = [
  { section: "math_1", questionCount: 30, timeLimitMinutes: 30 },
  { section: "math_2", questionCount: 30, timeLimitMinutes: 30 },
  { section: "reading", questionCount: 30, timeLimitMinutes: 45 },
  { section: "analogies", questionCount: 30, timeLimitMinutes: 30 },
  { section: "grammar", questionCount: 30, timeLimitMinutes: 35 },
];

function ExamRunnerContent() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { lang, t } = useTranslation();

  const testId = (params?.testId as string) || "ort_main_standard";
  const pinParam = searchParams.get("pin");

  // Session state
  const [attemptId, setAttemptId] = useState<string>("");
  const [sections, setSections] = useState<SectionItem[]>(DEFAULT_SECTIONS);
  const [questionsBySection, setQuestionsBySection] = useState<Record<string, QuestionItem[]>>({});
  const [loadingSession, setLoadingSession] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [maxAttemptsExceeded, setMaxAttemptsExceeded] = useState<{ isExceeded: boolean; message: string } | null>(null);

  // PIN Access Code state
  const [requiresPin, setRequiresPin] = useState(false);
  const [enteredPin, setEnteredPin] = useState(pinParam || "");
  const [pinError, setPinError] = useState<string | null>(null);
  const [isVerifyingPin, setIsVerifyingPin] = useState(false);

  // Active section & question state
  const [currentSectionIndex, setCurrentSectionIndex] = useState(0);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<
    Record<string, { selectedOptionId?: string; flagged?: boolean; timeSpentSeconds?: number }>
  >({});

  // Static Manual Section Transition Interstitial State
  const [isTransitioning, setIsTransitioning] = useState(false);

  // Final submission & score state
  const [isSubmittingFinal, setIsSubmittingFinal] = useState(false);
  const [finalResult, setFinalResult] = useState<MockTestFinalResult | null>(null);

  // Section names dictionary
  const getSectionName = (secCode: string) => {
    switch (secCode) {
      case "math_1":
        return lang === "ky" ? "1-Бөлүм: Математика I" : "Раздел 1: Математика I";
      case "math_2":
        return lang === "ky" ? "2-Бөлүм: Математика II (Салыштыруу)" : "Раздел 2: Математика II (Сравнение)";
      case "reading":
        return lang === "ky" ? "3-Бөлүм: Окуу жана түшүнүү" : "Раздел 3: Чтение и понимание";
      case "analogies":
        return lang === "ky" ? "4-Бөлүм: Аналогиялар" : "Раздел 4: Аналогии";
      case "grammar":
        return lang === "ky" ? "5-Бөлүм: Практикалык грамматика" : "Раздел 5: Практическая грамматика";
      case "chemistry":
        return lang === "ky" ? "Химия" : "Химия";
      case "biology":
        return lang === "ky" ? "Биология" : "Биология";
      case "physics":
        return lang === "ky" ? "Физика" : "Физика";
      case "history":
        return lang === "ky" ? "Тарых" : "История";
      case "english":
        return lang === "ky" ? "Англис тили" : "Английский язык";
      default:
        return secCode;
    }
  };

  // Initialize test session with backend
  const initSession = useCallback(
    async (customPin?: string) => {
      const activePin =
        customPin !== undefined ? customPin : (pinParam || undefined);

      try {
        setLoadingSession(true);
        setSessionError(null);

        const authHeader = await getAuthHeader();
        const res = await fetch("/api/v1/mock-tests/start", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...authHeader,
          },
          body: JSON.stringify({
            templateId: testId,
            language: lang,
            access_code: activePin || undefined,
            pin: activePin || undefined,
          }),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          const errMsg = err.detail || "Failed to start exam session";

          const isPinError =
            res.status === 403 &&
            (errMsg.includes("PIN") ||
             errMsg.includes("кирүү коду") ||
             errMsg.includes("код доступа") ||
             errMsg.toLowerCase().includes("access code"));

          if (isPinError) {
            setRequiresPin(true);
            if (activePin) {
              setPinError(
                lang === "ky"
                  ? "Туура эмес 4 орундуу PIN-код!"
                  : "Неверный 4-значный PIN-код!"
              );
            } else {
              setPinError(null);
            }
            return;
          }

          const isMaxAttempts =
            res.status === 403 &&
            (errMsg.includes("максималдуу аракеттер") ||
             errMsg.includes("Лимит попыток") ||
             errMsg.includes("max_attempts") ||
             errMsg.toLowerCase().includes("maximum number of attempts"));

          if (isMaxAttempts) {
            setMaxAttemptsExceeded({ isExceeded: true, message: errMsg });
            return;
          }

          throw new Error(errMsg);
        }

        const data = await res.json();
        setRequiresPin(false);
        setPinError(null);
        setAttemptId(data.attemptId);

        // Hydrate locally cached answers or backend answers
        try {
          const cached = localStorage.getItem(`ort_attempt_answers_${data.attemptId}`);
          if (cached) {
            setAnswers(JSON.parse(cached));
          } else if (data.answers) {
            setAnswers(data.answers);
          }
        } catch (e) {
          console.warn("Error hydrating cached answers:", e);
        }

        const rawSections: SectionItem[] =
          Array.isArray(data.sections) && data.sections.length > 0
            ? data.sections
            : DEFAULT_SECTIONS;
        const questionsMap = data.questions || {};
        setQuestionsBySection(questionsMap);

        // Strictly sort sections by STRICT_SECTION_ORDER
        const sortedSections = [...rawSections].sort((a, b) => {
          const idxA = STRICT_SECTION_ORDER.indexOf(a.section);
          const idxB = STRICT_SECTION_ORDER.indexOf(b.section);
          return (idxA !== -1 ? idxA : 999) - (idxB !== -1 ? idxB : 999);
        });

        // Filter out sections that have 0 questions if questions exist
        const hasAnyQuestions = Object.values(questionsMap).some(
          (arr: any) => Array.isArray(arr) && arr.length > 0
        );
        const validSections = hasAnyQuestions
          ? sortedSections.filter(
              (s) => Array.isArray(questionsMap[s.section]) && questionsMap[s.section].length > 0
            )
          : sortedSections;

        setSections(validSections.length > 0 ? validSections : DEFAULT_SECTIONS);
      } catch (err: any) {
        console.error("Session start error:", err);
        setSessionError(err.message || "Failed to start exam");
      } finally {
        setLoadingSession(false);
      }
    },
    [testId, lang, pinParam]
  );

  useEffect(() => {
    initSession();
  }, [initSession]);

  const handlePinSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!enteredPin.trim()) {
      setPinError(lang === "ky" ? "Кирүү кодун жазыңыз" : "Введите код доступа");
      return;
    }
    setIsVerifyingPin(true);
    await initSession(enteredPin.trim());
    setIsVerifyingPin(false);
  };

  const activeSection = sections[currentSectionIndex] || sections[0];
  const activeQuestions = useMemo(() => {
    return questionsBySection[activeSection?.section] || [];
  }, [questionsBySection, activeSection]);

  const currentQuestion = activeQuestions[currentIndex] || activeQuestions[0];
  const questionIds = useMemo(() => activeQuestions.map((q) => q.id), [activeQuestions]);

  const isFinalSection = currentSectionIndex >= sections.length - 1;
  const nextSection = !isFinalSection ? sections[currentSectionIndex + 1] : null;

  // Bluebook conditional layout check
  const hasRichContent = Boolean(
    currentQuestion && (currentQuestion.passage_text || currentQuestion.image_url)
  );

  // Batch sync answers to backend
  const batchSyncAnswers = async () => {
    if (!attemptId) return;
    try {
      const authHeader = await getAuthHeader();
      await fetch(`/api/v1/mock-tests/${attemptId}/save`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeader,
        },
        body: JSON.stringify({ answers }),
      });
    } catch (e) {
      console.warn("Batch sync failed:", e);
    }
  };

  const handleSelectOption = (optionId: string) => {
    if (!currentQuestion) return;
    setAnswers((prev) => {
      const updated = {
        ...prev,
        [currentQuestion.id]: {
          ...prev[currentQuestion.id],
          selectedOptionId: optionId,
          timeSpentSeconds: (prev[currentQuestion.id]?.timeSpentSeconds || 0) + 5,
        },
      };
      if (attemptId) {
        try {
          localStorage.setItem(`ort_attempt_answers_${attemptId}`, JSON.stringify(updated));
        } catch (e) {
          console.warn("Failed to cache answers to localStorage:", e);
        }
      }
      return updated;
    });
  };

  const handleToggleFlag = () => {
    if (!currentQuestion) return;
    setAnswers((prev) => {
      const updated = {
        ...prev,
        [currentQuestion.id]: {
          ...prev[currentQuestion.id],
          flagged: !prev[currentQuestion.id]?.flagged,
        },
      };
      if (attemptId) {
        try {
          localStorage.setItem(`ort_attempt_answers_${attemptId}`, JSON.stringify(updated));
        } catch (e) {
          console.warn("Failed to cache answers to localStorage:", e);
        }
      }
      return updated;
    });
  };

  // Section time expired or student clicks Finish Section
  const handleSectionTimeExpiredOrFinish = () => {
    setIsTransitioning(true);
  };

  // Complete Transition: student manually clicks Continue button to enter next section or submit
  const handleCompleteTransition = async () => {
    setIsTransitioning(false);

    if (isFinalSection) {
      // Final Section completed -> submit entire exam
      await handleSubmitFinalTest();
    } else {
      // High-concurrency batch sync before switching section
      await batchSyncAnswers();
      // Move to next section
      setCurrentSectionIndex((prev) => prev + 1);
      setCurrentIndex(0);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  // Final Exam Submission
  const handleSubmitFinalTest = async () => {
    setIsSubmittingFinal(true);
    try {
      const authHeader = await getAuthHeader();
      const res = await fetch(`/api/v1/mock-tests/${attemptId}/submit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeader,
        },
        body: JSON.stringify({ answers }),
      });

      if (!res.ok) {
        throw new Error("Failed to submit exam");
      }

      const result = await res.json();
      // Clear localStorage cache on successful test submission
      try {
        localStorage.removeItem(`ort_attempt_answers_${attemptId}`);
      } catch {}
      setFinalResult(result);
    } catch (err: any) {
      alert(err.message || "Submission failed");
    } finally {
      setIsSubmittingFinal(false);
    }
  };

  // PIN Access Code Required Screen
  if (requiresPin && !attemptId) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-3xl border border-slate-200/80 p-8 text-center space-y-6 shadow-xl shadow-slate-100">
          <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mx-auto shadow-xs">
            <KeyRound className="w-8 h-8" />
          </div>

          <div className="space-y-2">
            <h3 className="font-extrabold text-slate-900 text-xl tracking-tight">
              {lang === "ky" ? "Экзаменге кирүү коду" : "Код доступа к экзамену"}
            </h3>
            <p className="text-xs text-slate-500 leading-relaxed max-w-xs mx-auto">
              {lang === "ky"
                ? "Бул сыноо тестине кирүү үчүн 4 орундуу PIN-кодду жазыңыз."
                : "Для прохождения данного теста введите 4-значный PIN-код доступа."}
            </p>
          </div>

          <form onSubmit={handlePinSubmit} className="space-y-4">
            <div>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={4}
                value={enteredPin}
                onChange={(e) => {
                  const val = e.target.value.replace(/[^0-9]/g, "").slice(0, 4);
                  setEnteredPin(val);
                  if (pinError) setPinError(null);
                }}
                placeholder="0000"
                autoFocus
                className="w-48 mx-auto text-center tracking-[0.5em] text-2xl font-mono font-bold py-3 px-4 bg-slate-50 border border-slate-200 rounded-2xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition"
              />
              {pinError && (
                <div className="flex items-center justify-center gap-1.5 mt-2.5 text-xs font-semibold text-rose-600">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                  <span>{pinError}</span>
                </div>
              )}
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-2 pt-2">
              <Link
                href={`/${lang}/mock-tests`}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>{lang === "ky" ? "Артка кайтуу" : "Назад к тестам"}</span>
              </Link>

              <button
                type="submit"
                disabled={isVerifyingPin || enteredPin.length !== 4}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl text-xs font-bold transition shadow-xs cursor-pointer"
              >
                {isVerifyingPin ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="w-4 h-4" />
                )}
                <span>{lang === "ky" ? "Кирүү жана баштоо" : "Войти и начать"}</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  // Max attempts exceeded screen
  if (maxAttemptsExceeded) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-3xl border border-slate-200 p-8 text-center space-y-5 shadow-sm">
          <div className="w-14 h-14 rounded-2xl bg-amber-50 text-amber-600 flex items-center justify-center mx-auto border border-amber-200">
            <AlertCircle className="w-7 h-7" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 text-lg">
              {lang === "ky" ? "Аракеттердин чеги бүттү" : "Лимит попыток исчерпан"}
            </h3>
            <p className="text-xs text-slate-500 mt-2 leading-relaxed">
              {lang === "ky"
                ? "Сиз бул экзаменди тапшыруу үчүн берилген максималдуу аракеттер санын толук колдондуңуз. Сиздин бардык жыйынтыктарыңыз сакталган."
                : "Вы достигли максимального количества попыток для этого экзамена. Ваши результаты успешно сохранены в системе."}
            </p>
          </div>
          <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              href={`/${lang}/mock-tests`}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition shadow-xs"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>{lang === "ky" ? "Сыноо тесттерге кайтуу" : "К списку тестов"}</span>
            </Link>
            <Link
              href={`/${lang}/progress`}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-slate-100 text-slate-700 rounded-xl text-xs font-semibold hover:bg-slate-200 transition"
            >
              <span>{lang === "ky" ? "Статистиканы көрүү" : "Моя статистика"}</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Error screen
  if (sessionError) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-3xl border border-slate-200 p-8 text-center space-y-4 shadow-sm">
          <div className="w-12 h-12 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center mx-auto">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <h3 className="font-bold text-slate-900 text-lg">
            {lang === "ky" ? "Экзамен башталган жок" : "Ошибка запуска экзамена"}
          </h3>
          <p className="text-xs text-slate-500 leading-relaxed">{sessionError}</p>
          <div className="pt-2">
            <Link
              href={`/${lang}/mock-tests`}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>{lang === "ky" ? "Сыноо тесттерине кайтуу" : "Назад к списку тестов"}</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Loading screen
  if (loadingSession) {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center gap-3 text-slate-400">
        <RefreshCw className="w-8 h-8 animate-spin text-indigo-600" />
        <span className="text-sm font-medium">{t("common.loading")}</span>
      </div>
    );
  }

  // Final Results Screen
  if (finalResult) {
    return (
      <div className="max-w-4xl mx-auto py-8 space-y-6">
        <div className="bg-white rounded-3xl border border-slate-200 p-8 shadow-sm text-center space-y-4">
          <div className="w-16 h-16 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto shadow-xs">
            <Award className="w-9 h-9" />
          </div>

          <h2 className="text-2xl font-extrabold text-slate-900">
            {lang === "ky" ? "Сынак ийгиликтүү аяктады!" : "Экзамен успешно завершен!"}
          </h2>

          <p className="text-sm text-slate-500 max-w-md mx-auto">
            {lang === "ky"
              ? "Бардык 5 бөлүм тапшырылды. Сиздин ОРТ нормативдик шкаласындагы упайыңыз:"
              : "Все разделы завершены. Ваш итоговый результат по нормативной шкале ОРТ:"}
          </p>

          <div className="py-4">
            <span className="text-5xl font-extrabold text-indigo-600 tracking-tight">
              {finalResult.totalScaledScore}
            </span>
            <span className="text-sm text-slate-400 block mt-1">
              {lang === "ky" ? "балл (60 — 245)" : "баллов (60 — 245)"}
            </span>
            {finalResult.isGoldenCertificate && (
              <span className="inline-block mt-2 px-3 py-1 bg-amber-100 text-amber-900 border border-amber-300 rounded-full text-xs font-bold">
                ⭐ {lang === "ky" ? "Алтын Сертификат деңгээли!" : "Уровень Золотого Сертификата!"}
              </span>
            )}
          </div>

          {/* Section Breakdown Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-left pt-4 border-t border-slate-100">
            {Object.entries(finalResult.sectionScores || {}).map(([sec, sc]) => (
              <div key={sec} className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] font-bold text-slate-400 uppercase block truncate">
                  {sec}
                </span>
                <span className="text-lg font-bold text-slate-900 block mt-0.5">
                  {sc.scaledScore}
                </span>
                <span className="text-[11px] text-emerald-600 font-semibold block">
                  {sc.rawScore} / {sc.totalQuestions} ({sc.accuracyPercentage}%)
                </span>
              </div>
            ))}
          </div>

          <div className="pt-6 flex flex-wrap items-center justify-center gap-3">
            <Link
              href={`/${lang}/mistakes`}
              className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold shadow-sm transition"
            >
              {lang === "ky" ? "Каталарды талдоо" : "Разбор ошибок"}
            </Link>
            <Link
              href={`/${lang}/mock-tests`}
              className="px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition"
            >
              {lang === "ky" ? "Сыноо тесттерге кайтуу" : "К списку тестов"}
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-16">
      {/* STATIC MANUAL SECTION TRANSITION INTERSTITIAL MODAL */}
      {isTransitioning && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-md p-4 animate-in fade-in">
          <div className="bg-white w-full max-w-md rounded-3xl p-8 text-center space-y-6 shadow-2xl border border-slate-100">
            <div className="w-16 h-16 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-8 h-8" />
            </div>

            <div>
              <h3 className="text-lg font-bold text-slate-900">
                {lang === "ky"
                  ? "Бөлүм аяктады. Сиздин жоопторуңуз сакталды"
                  : "Раздел завершен. Ваши ответы сохранены"}
              </h3>
            </div>

            {/* Next Section Details */}
            {!isFinalSection && nextSection ? (
              <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-4 text-left space-y-3">
                <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                  {lang === "ky" ? "Кийинки бөлүм" : "Следующий раздел"}
                </div>
                <div className="text-base font-bold text-slate-900">
                  {getSectionName(nextSection.section)}
                </div>
                <div className="flex items-center gap-4 text-xs text-slate-600">
                  <div className="flex items-center gap-1.5 font-medium">
                    <FileText className="w-4 h-4 text-indigo-500" />
                    <span>{nextSection.questionCount || 30} {lang === "ky" ? "суроо" : "вопросов"}</span>
                  </div>
                  <div className="flex items-center gap-1.5 font-medium">
                    <Clock className="w-4 h-4 text-indigo-500" />
                    <span>
                      {nextSection.timeLimitMinutes > 0
                        ? `${nextSection.timeLimitMinutes} ${lang === "ky" ? "мүнөт" : "минут"}`
                        : (lang === "ky" ? "Чектөөсүз" : "Без лимита")}
                    </span>
                  </div>
                </div>
                <p className="text-[11px] text-slate-500 pt-2 border-t border-slate-200/60 leading-relaxed">
                  {lang === "ky"
                    ? "Даяр болгондо 'Кийинки бөлүмгө өтүү' баскычын басыңыз. Убакыт басылгандан кийин гана эсептеле баштайт."
                    : "Нажмите 'Продолжить', когда будете готовы. Таймер нового раздела начнется только после нажатия."}
                </p>
              </div>
            ) : (
              <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4 text-emerald-800 text-xs text-left leading-relaxed">
                {lang === "ky"
                  ? "Бардык бөлүмдөр аяктады! Тестти толугу менен тапшырып, расмий баллдарды көрүү үчүн төмөнкү баскычты басыңыз."
                  : "Все разделы экзамена завершены! Нажмите кнопку ниже, чтобы отправить результаты и просмотреть итоговую шкалу баллов."}
              </div>
            )}

            <div>
              {!isFinalSection ? (
                <button
                  onClick={handleCompleteTransition}
                  className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold shadow-md hover:shadow-lg transition flex items-center justify-center gap-2"
                >
                  <span>{lang === "ky" ? "Кийинки бөлүмгө өтүү" : "Продолжить"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              ) : (
                <button
                  onClick={handleCompleteTransition}
                  disabled={isSubmittingFinal}
                  className="w-full py-3.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-bold shadow-md hover:shadow-lg transition flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {isSubmittingFinal && <RefreshCw className="w-4 h-4 animate-spin" />}
                  <span>
                    {lang === "ky"
                      ? "Тестти аяктоо жана жыйынтыкты көрүү"
                      : "Завершить тест и посмотреть результаты"}
                  </span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TOP CBT EXAM BAR */}
      <div className="sticky top-0 z-30 bg-white/95 backdrop-blur-md rounded-2xl border border-slate-200/80 px-6 py-3.5 shadow-xs flex items-center justify-between gap-4">
        {/* Section title & progress */}
        <div className="flex items-center gap-3">
          <span className="p-1.5 rounded-lg bg-indigo-50 text-indigo-600">
            <Layers className="w-4 h-4" />
          </span>
          <div>
            <span className="text-xs font-bold text-slate-900 block">
              {getSectionName(activeSection.section)}
            </span>
            <span className="text-[11px] text-slate-400">
              {currentSectionIndex + 1} / {sections.length} {lang === "ky" ? "бөлүм" : "раздел"}
            </span>
          </div>
        </div>

        {/* Timer */}
        <div className="flex items-center gap-3">
          <ExamTimer
            key={`timer_${activeSection.section}`}
            initialSeconds={activeSection.timeLimitMinutes > 0 ? activeSection.timeLimitMinutes * 60 : null}
            onTimeExpired={handleSectionTimeExpiredOrFinish}
          />

          <button
            onClick={handleSectionTimeExpiredOrFinish}
            className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-rose-50 hover:text-rose-700 text-slate-700 rounded-xl text-xs font-semibold transition"
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            <span>
              {isFinalSection
                ? lang === "ky"
                  ? "Экзаменди аяктоо"
                  : "Завершить экзамен"
                : lang === "ky"
                ? "Бөлүмдү тапшыруу"
                : "Завершить раздел"}
            </span>
          </button>
        </div>
      </div>

      {/* BLUEBOOK CONDITIONAL EXAM AREA */}
      {hasRichContent ? (
        /* 50/50 SPLIT-SCREEN LAYOUT FOR PASSAGE / IMAGE QUESTIONS */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: Reading Passage & Image (Independent Scroll) */}
          <div className="lg:col-span-6 space-y-4 max-h-[calc(100vh-170px)] overflow-y-auto pr-1">
            {/* Diagram Image if available */}
            {currentQuestion.image_url && (
              <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-xs">
                <div className="text-[11px] font-bold text-purple-700 uppercase tracking-wider mb-2 flex items-center gap-1">
                  <ImageIcon className="w-3.5 h-3.5" />
                  <span>{lang === "ky" ? "Диаграмма / Геометрия" : "Диаграмма / Чертеж"}</span>
                </div>
                <img
                  src={currentQuestion.image_url}
                  alt="Problem figure"
                  className="max-w-full max-h-72 mx-auto object-contain rounded-lg"
                />
              </div>
            )}

            {/* Reading Passage if available */}
            {currentQuestion.passage_text && (
              <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-3 font-serif leading-relaxed text-sm text-slate-800">
                <div className="text-[11px] font-sans font-bold text-indigo-700 uppercase tracking-wider flex items-center gap-1.5 border-b border-slate-100 pb-2">
                  <FileText className="w-4 h-4" />
                  <span>{lang === "ky" ? "Окуу тексти (Passage)" : "Материал для чтения"}</span>
                </div>
                <div className="whitespace-pre-line text-slate-800">
                  {currentQuestion.passage_text}
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Question Card + Palette */}
          <div className="lg:col-span-6 space-y-6">
            {currentQuestion && (
              <QuestionCard
                question={currentQuestion}
                questionNumber={currentIndex + 1}
                totalQuestions={activeQuestions.length}
                selectedOptionId={answers[currentQuestion.id]?.selectedOptionId}
                isFlagged={Boolean(answers[currentQuestion.id]?.flagged)}
                onSelectOption={handleSelectOption}
                onToggleFlag={handleToggleFlag}
              />
            )}

            {/* Navigation buttons */}
            <div className="flex items-center justify-between gap-3">
              <button
                onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
                disabled={currentIndex === 0}
                className="px-4 py-2 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-50 transition disabled:opacity-40 flex items-center gap-1.5"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>{t("common.back")}</span>
              </button>

              <button
                onClick={() => {
                  if (currentIndex < activeQuestions.length - 1) {
                    setCurrentIndex((prev) => prev + 1);
                  } else {
                    handleSectionTimeExpiredOrFinish();
                  }
                }}
                className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold shadow-xs transition flex items-center gap-1.5"
              >
                <span>
                  {currentIndex < activeQuestions.length - 1
                    ? t("common.next")
                    : isFinalSection
                    ? lang === "ky"
                      ? "Экзаменди аяктоо"
                      : "Завершить тест"
                    : lang === "ky"
                    ? "Кийинки бөлүм"
                    : "Следующий раздел"}
                </span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Question Palette */}
            <QuestionPalette
              totalQuestions={activeQuestions.length}
              currentIndex={currentIndex}
              onSelectIndex={setCurrentIndex}
              answers={answers}
              questionIds={questionIds}
            />
          </div>
        </div>
      ) : (
        /* SINGLE-COLUMN CENTERED LAYOUT FOR STANDARD QUESTIONS */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <div className="lg:col-span-8 max-w-3xl w-full mx-auto space-y-6">
            {currentQuestion ? (
              <QuestionCard
                question={currentQuestion}
                questionNumber={currentIndex + 1}
                totalQuestions={activeQuestions.length}
                selectedOptionId={answers[currentQuestion.id]?.selectedOptionId}
                isFlagged={Boolean(answers[currentQuestion.id]?.flagged)}
                onSelectOption={handleSelectOption}
                onToggleFlag={handleToggleFlag}
              />
            ) : (
              <div className="p-8 text-center bg-white rounded-2xl border border-slate-200 text-slate-400">
                Суроолор жүктөлүүдө...
              </div>
            )}

            {/* Navigation buttons */}
            <div className="flex items-center justify-between gap-3">
              <button
                onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
                disabled={currentIndex === 0}
                className="px-4 py-2 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-50 transition disabled:opacity-40 flex items-center gap-1.5"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>{t("common.back")}</span>
              </button>

              <button
                onClick={() => {
                  if (currentIndex < activeQuestions.length - 1) {
                    setCurrentIndex((prev) => prev + 1);
                  } else {
                    handleSectionTimeExpiredOrFinish();
                  }
                }}
                className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold shadow-xs transition flex items-center gap-1.5"
              >
                <span>
                  {currentIndex < activeQuestions.length - 1
                    ? t("common.next")
                    : isFinalSection
                    ? lang === "ky"
                      ? "Экзаменди аяктоо"
                      : "Завершить тест"
                    : lang === "ky"
                    ? "Кийинки бөлүм"
                    : "Следующий раздел"}
                </span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Sidebar Palette */}
          <div className="lg:col-span-4">
            <QuestionPalette
              totalQuestions={activeQuestions.length}
              currentIndex={currentIndex}
              onSelectIndex={setCurrentIndex}
              answers={answers}
              questionIds={questionIds}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default function ExamRunnerPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-[70vh] flex flex-col items-center justify-center gap-3 text-slate-400">
          <RefreshCw className="w-8 h-8 animate-spin text-indigo-600" />
          <span className="text-sm font-medium">Жүктөлүүдө...</span>
        </div>
      }
    >
      <ExamRunnerContent />
    </Suspense>
  );
}
