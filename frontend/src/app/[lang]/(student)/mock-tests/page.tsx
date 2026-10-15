"use client";

export const dynamic = "force-dynamic";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import {
  Clock,
  Award,
  Zap,
  Layers,
  ArrowRight,
  Lock,
  Unlock,
  KeyRound,
  Calendar,
  AlertCircle,
  X,
  RefreshCw,
  BookOpenCheck,
  Compass,
  RotateCcw,
  CheckCircle2,
  BarChart3,
} from "lucide-react";
import { getAuthHeader } from "@/lib/api";

interface ExamSetItem {
  id: string;
  type?: string;
  exam_type?: "full_main" | "subject" | "practice_bank";
  title: string;
  description?: string;
  language: string;
  status: "draft" | "published";
  available_from?: string | null;
  available_until?: string | null;
  access_code?: string | null;
  max_attempts: number;
  totalQuestions: number;
  totalTimeMinutes: number;
  time_limit_minutes?: number | null;
  question_count?: number;
  user_attempts_count?: number;
  completionsCount?: number;
  sections?: Array<{ section: string; questionCount: number; timeLimitMinutes: number }>;
  has_in_progress?: boolean;
  in_progress_attempt_id?: string | null;
}

export default function MockTestsHubPage() {
  const { lang, t } = useTranslation();
  const router = useRouter();

  const [exams, setExams] = useState<ExamSetItem[]>([]);
  const [inProgressMap, setInProgressMap] = useState<Record<string, any>>({});
  const [completedAttemptsMap, setCompletedAttemptsMap] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);

  // PIN Access Code Modal State
  const [pinModalExam, setPinModalExam] = useState<ExamSetItem | null>(null);
  const [enteredPin, setEnteredPin] = useState("");
  const [pinError, setPinError] = useState<string | null>(null);

  const fetchExams = async () => {
    try {
      setLoading(true);
      const authHeader = await getAuthHeader();
      const [resExams, resInProg, resAttempts] = await Promise.all([
        fetch(`/api/v1/exam-sets/student?lang=${lang}`, { headers: authHeader, cache: "no-store" }),
        fetch(`/api/v1/mock-tests/in-progress`, { headers: authHeader, cache: "no-store" }).catch(() => null),
        fetch(`/api/v1/mock-tests/attempts`, { headers: authHeader, cache: "no-store" }).catch(() => null),
      ]);

      const inProgObj: Record<string, any> = {};
      if (resInProg && resInProg.ok) {
        const inProgList = await resInProg.json().catch(() => []);
        if (Array.isArray(inProgList)) {
          for (const item of inProgList) {
            if (item.templateId) {
              inProgObj[item.templateId] = item;
            }
          }
        }
      }
      setInProgressMap(inProgObj);

      const completedObj: Record<string, any> = {};
      if (resAttempts && resAttempts.ok) {
        const attemptsList = await resAttempts.json().catch(() => []);
        if (Array.isArray(attemptsList)) {
          for (const item of attemptsList) {
            const tid = item.templateId || item.id;
            if (tid && !completedObj[tid]) {
              completedObj[tid] = item;
            }
          }
        }
      }
      setCompletedAttemptsMap(completedObj);

      if (resExams.ok) {
        const data = await resExams.json();
        if (Array.isArray(data)) {
          const uniqueExams: ExamSetItem[] = Array.from(
            new Map(
              data.map((item: any) => {
                const inProg = inProgObj[item.id];
                const comp = completedObj[item.id];
                let hasInProg = Boolean(item.has_in_progress);
                if (inProg && comp) {
                  const inProgTime = new Date(inProg.startedAt || inProg.createdAt || 0).getTime();
                  const compTime = new Date(comp.completedAt || comp.startedAt || 0).getTime();
                  hasInProg = inProgTime > compTime;
                } else if (inProg) {
                  hasInProg = true;
                } else if (comp) {
                  hasInProg = false;
                }
                const attemptsCount = item.user_attempts_count ?? (comp ? 1 : 0);
                return [item.id, { ...item, has_in_progress: hasInProg, user_attempts_count: attemptsCount }];
              })
            ).values()
          );
          setExams(uniqueExams);
        }
      }
    } catch (err) {
      console.error("Failed to load exam sets:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExams();
  }, [lang]);

  const handleStartExamClick = (exam: ExamSetItem) => {
    const isResuming = Boolean(exam.has_in_progress || inProgressMap[exam.id]);

    // Check if max attempts reached (only when starting a brand new attempt)
    if (!isResuming) {
      const attemptsCount = exam.user_attempts_count ?? 0;
      const maxAttempts = exam.max_attempts ?? 1;
      if (maxAttempts < 99 && attemptsCount >= maxAttempts) {
        alert(
          lang === "ky"
            ? `Сиз бул тест боюнча бардык мүмкүн болгон аракеттерди колдондуңуз (${attemptsCount}/${maxAttempts}).`
            : `Вы исчерпали лимит попыток для этого экзамена (${attemptsCount}/${maxAttempts}).`
        );
        return;
      }
    }

    // Check if locked by date
    const nowIso = new Date().toISOString();
    if (exam.available_from && nowIso < exam.available_from) {
      alert(
        lang === "ky"
          ? `Экзамен ${new Date(exam.available_from).toLocaleString()} башталат`
          : `Экзамен откроется ${new Date(exam.available_from).toLocaleString()}`
      );
      return;
    }
    if (exam.available_until && nowIso > exam.available_until) {
      alert(
        lang === "ky"
          ? "Экзамендин мөөнөтү бүттү (Заблокирован)"
          : "Срок сдачи экзамена истек (Заблокирован)"
      );
      return;
    }

    // Check if PIN required
    if (exam.access_code && exam.access_code.trim()) {
      setPinModalExam(exam);
      setEnteredPin("");
      setPinError(null);
      return;
    }

    // Navigate directly into exam runner
    router.push(`/${lang}/mock-tests/${exam.id}`);
  };

  const handleRetakeExamClick = (exam: ExamSetItem) => {
    // Check if locked by date
    const nowIso = new Date().toISOString();
    if (exam.available_from && nowIso < exam.available_from) {
      alert(
        lang === "ky"
          ? `Экзамен ${new Date(exam.available_from).toLocaleString()} башталат`
          : `Экзамен откроется ${new Date(exam.available_from).toLocaleString()}`
      );
      return;
    }
    if (exam.available_until && nowIso > exam.available_until) {
      alert(
        lang === "ky"
          ? "Экзамендин мөөнөтү бүттү (Заблокирован)"
          : "Срок сдачи экзамена истек (Заблокирован)"
      );
      return;
    }

    if (exam.access_code && exam.access_code.trim()) {
      setPinModalExam({ ...exam, isRetake: true } as any);
      setEnteredPin("");
      setPinError(null);
      return;
    }

    router.push(`/${lang}/mock-tests/${exam.id}?force_new=true`);
  };

  const handleViewResult = (examId: string, completedAttempt?: any) => {
    if (completedAttempt?.result) {
      try {
        sessionStorage.setItem(`ort_result_${examId}`, JSON.stringify(completedAttempt.result));
      } catch {}
    }
    router.push(`/${lang}/mock-tests/${examId}/result`);
  };

  const handleVerifyPinAndStart = (e: React.FormEvent) => {
    e.preventDefault();
    if (!pinModalExam) return;

    if (enteredPin.trim() !== pinModalExam.access_code?.trim()) {
      setPinError(
        lang === "ky" ? "Туура эмес 4 орундуу PIN-код!" : "Неверный 4-значный PIN-код!"
      );
      return;
    }

    const examId = pinModalExam.id;
    const pin = enteredPin.trim();
    const isRetake = (pinModalExam as any).isRetake;
    setPinModalExam(null);
    const query = new URLSearchParams();
    query.set("pin", pin);
    if (isRetake) {
      query.set("force_new", "true");
    }
    router.push(`/${lang}/mock-tests/${examId}?${query.toString()}`);
  };

  const fullMainExams = exams.filter(
    (e) =>
      (e.exam_type === "full_main" || e.type === "fixed_full" || (!e.exam_type && !e.id.toLowerCase().includes("subject"))) &&
      e.exam_type !== "practice_bank" &&
      e.exam_type !== "subject" &&
      e.type !== "subject" &&
      !e.id.toLowerCase().includes("subject")
  );
  const subjectExams = exams.filter(
    (e) => e.exam_type === "subject" || e.type === "subject" || e.id.toLowerCase().includes("subject")
  );

  const fastPracticeId = lang === "ru" ? "exam_practice_bank_ru" : "exam_practice_bank_ky";
  const fastPracticeInProg =
    inProgressMap[fastPracticeId] ||
    inProgressMap["ort_speed_drill"] ||
    inProgressMap["exam_practice_bank_ky"] ||
    inProgressMap["exam_practice_bank_ru"];
  const fastPracticeComp =
    completedAttemptsMap[fastPracticeId] ||
    completedAttemptsMap["ort_speed_drill"] ||
    completedAttemptsMap["exam_practice_bank_ky"] ||
    completedAttemptsMap["exam_practice_bank_ru"];

  let isFastPracticeResuming = false;
  if (fastPracticeInProg) {
    if (fastPracticeComp) {
      const inProgTime = new Date(fastPracticeInProg.startedAt || fastPracticeInProg.createdAt || 0).getTime();
      const compTime = new Date(fastPracticeComp.completedAt || fastPracticeComp.startedAt || 0).getTime();
      isFastPracticeResuming = inProgTime > compTime;
    } else {
      isFastPracticeResuming = true;
    }
  }

  const renderExamCard = (test: ExamSetItem) => {
    const isResuming = Boolean(test.has_in_progress || inProgressMap[test.id]);
    const completedAttempt = completedAttemptsMap[test.id];
    const attemptsCount = test.user_attempts_count ?? (completedAttempt ? 1 : 0);
    const maxAttempts = test.max_attempts ?? 1;
    const isUnlimitedAttempts = maxAttempts >= 99;
    const isAttemptsExceeded = !isUnlimitedAttempts && attemptsCount >= maxAttempts;
    const isCompleted = !isResuming && (attemptsCount > 0 || Boolean(completedAttempt));
    const canRetake = isCompleted && (isUnlimitedAttempts || attemptsCount < maxAttempts);

    const nowIso = new Date().toISOString();
    const isLockedEarly = test.available_from && nowIso < test.available_from;
    const isLockedLate = test.available_until && nowIso > test.available_until;
    const isLocked = Boolean(isLockedEarly || isLockedLate);
    const hasPin = Boolean(test.access_code && test.access_code.trim());

    // Custom timer calculation
    const timeMinutes = test.time_limit_minutes !== undefined && test.time_limit_minutes !== null
      ? test.time_limit_minutes
      : test.totalTimeMinutes;
    const timeDisplay = timeMinutes && timeMinutes > 0
      ? `${timeMinutes} ${lang === "ky" ? "мүнөт" : "минут"}`
      : (lang === "ky" ? "Чектөөсүз" : "Без ограничений");

    const isActionDisabled = !isResuming && !isCompleted && (isLocked || isAttemptsExceeded);

    return (
      <div
        key={test.id}
        className={`bg-white rounded-2xl border p-6 flex flex-col justify-between shadow-xs transition-all relative overflow-hidden ${
          isResuming
            ? "border-emerald-300 ring-1 ring-emerald-200/60 hover:shadow-md"
            : isCompleted
            ? "border-slate-200 hover:border-slate-300 hover:shadow-md"
            : isActionDisabled
            ? "border-slate-200 bg-slate-50/60 opacity-80"
            : "border-slate-200 hover:border-indigo-300 hover:shadow-md"
        }`}
      >
        <div>
          {/* Top Badges */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-1 rounded-lg bg-indigo-50 text-indigo-700 font-bold text-xs flex items-center gap-1.5">
                <BookOpenCheck className="w-3.5 h-3.5" />
                <span>
                  {test.question_count ?? test.totalQuestions ?? 150} {lang === "ky" ? "суроо" : "вопросов"}
                </span>
              </span>

              {hasPin && (
                <span className="px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 border border-amber-200 text-[11px] font-semibold flex items-center gap-1">
                  <KeyRound className="w-3 h-3" />
                  <span>PIN</span>
                </span>
              )}
            </div>

            {/* Lock / Attempt Status / In Progress Status */}
            {isResuming ? (
              <span className="inline-flex items-center gap-1 text-xs font-bold text-amber-700 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-200">
                <RotateCcw className="w-3.5 h-3.5" />
                <span>{lang === "ky" ? "Улантууда" : "В процессе"}</span>
              </span>
            ) : isCompleted ? (
              <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>{lang === "ky" ? "Аяктады" : "Завершен"}</span>
              </span>
            ) : isAttemptsExceeded ? (
              <span className="inline-flex items-center gap-1 text-xs font-bold text-rose-600 bg-rose-50 px-2.5 py-1 rounded-full border border-rose-200">
                <AlertCircle className="w-3.5 h-3.5" />
                <span>{lang === "ky" ? "Лимит бүттү" : "Лимит исчерпан"}</span>
              </span>
            ) : isLocked ? (
              <span className="inline-flex items-center gap-1 text-xs font-bold text-rose-600 bg-rose-50 px-2.5 py-1 rounded-full border border-rose-200">
                <Lock className="w-3.5 h-3.5" />
                <span>{lang === "ky" ? "Бөгөттөлгөн" : "Заблокирован"}</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-600 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
                <Unlock className="w-3.5 h-3.5" />
                <span>{lang === "ky" ? "Ачык" : "Доступен"}</span>
              </span>
            )}
          </div>

          {/* Title & Description */}
          <h4 className="text-base font-bold text-slate-900 mb-1">{test.title}</h4>
          <p className="text-xs text-slate-500 leading-relaxed mb-4">
            {test.description ||
              (lang === "ky"
                ? "Расмий ОРТ модели боюнча түзүлгөн сыноо тести."
                : "Пробный тест по стандартам общереспубликанского тестирования.")}
          </p>

          {/* Meta info */}
          <div className="grid grid-cols-2 gap-2 p-3 bg-slate-50 rounded-xl text-xs text-slate-600 border border-slate-100 mb-4">
            <div className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-slate-400" />
              <span>{timeDisplay}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
              <span className={isAttemptsExceeded && !isResuming ? "text-rose-600 font-bold" : ""}>
                {lang === "ky" ? "Аракеттер:" : "Попытки:"}{" "}
                {isUnlimitedAttempts
                  ? (lang === "ky" ? "Чектөөсүз" : "Без лимита")
                  : `${attemptsCount}/${maxAttempts}`}
              </span>
            </div>
            <div className="flex items-center gap-1.5 col-span-2 pt-1 border-t border-slate-200/50 text-[11px] text-slate-400">
              <Calendar className="w-3 h-3 text-slate-400" />
              <span>
                {lang === "ky" ? "Мөөнөтү:" : "Срок:"}{" "}
                {test.available_until
                  ? new Date(test.available_until).toLocaleDateString()
                  : lang === "ky"
                  ? "Чектөөсүз"
                  : "Бессрочно"}
              </span>
            </div>
          </div>
        </div>

        {/* Action Button(s) */}
        {isResuming ? (
          <button
            onClick={() => handleStartExamClick(test)}
            className="w-full py-2.5 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition shadow-xs cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white shadow-emerald-100"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>{lang === "ky" ? "Улантуу" : "Возобновить"}</span>
          </button>
        ) : isCompleted ? (
          <div className="flex flex-col gap-2">
            <button
              onClick={() => handleViewResult(test.id, completedAttempt)}
              className="w-full py-2.5 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition shadow-xs cursor-pointer bg-slate-900 hover:bg-slate-800 text-white"
            >
              <BarChart3 className="w-3.5 h-3.5" />
              <span>{lang === "ky" ? "Аяктады / Жыйынтыгын көрүү" : "Завершен / Посмотреть результат"}</span>
            </button>
            {canRetake && (
              <button
                onClick={() => handleRetakeExamClick(test)}
                className="w-full py-2 rounded-xl font-bold text-xs flex items-center justify-center gap-1.5 transition border border-indigo-200 text-indigo-700 bg-indigo-50/60 hover:bg-indigo-100 cursor-pointer"
              >
                <RotateCcw className="w-3 h-3" />
                <span>{lang === "ky" ? "Кайра тапшыруу" : "Пересдать"}</span>
              </button>
            )}
          </div>
        ) : (
          <button
            onClick={() => handleStartExamClick(test)}
            disabled={isActionDisabled}
            className={`w-full py-2.5 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition shadow-xs cursor-pointer ${
              isActionDisabled
                ? "bg-slate-200 text-slate-400 cursor-not-allowed"
                : "bg-indigo-600 hover:bg-indigo-700 text-white"
            }`}
          >
            {isAttemptsExceeded ? (
              <>
                <AlertCircle className="w-3.5 h-3.5" />
                <span>{lang === "ky" ? "Аракеттер чеги бүттү" : "Лимит попыток исчерпан"}</span>
              </>
            ) : isLocked ? (
              <>
                <Lock className="w-3.5 h-3.5" />
                <span>{lang === "ky" ? "Жабык" : "Недоступно"}</span>
              </>
            ) : (
              <>
                <span>{lang === "ky" ? "Тестти баштоо" : "Начать тест"}</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-10 pb-12 max-w-6xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-slate-900 tracking-tight">
          {lang === "ky" ? "ЖРТ Сыноо Тесттери" : "Пробные Тесты ОРТ"}
        </h2>
        <p className="text-sm text-slate-500 mt-1">
          {lang === "ky"
            ? "Реалдуу ОРТ форматындагы бөлүм-бөлүмү менен убакытка чектелген тесттер жана ылдам машыгуу."
            : "Посекционные тесты в условиях реального ОРТ и экспресс-тренировка темпа решения."}
        </p>
      </div>

      {/* ZONE 1: Fast Practice Hero Card */}
      <div className="bg-gradient-to-r from-emerald-900 via-emerald-800 to-slate-900 text-white rounded-3xl p-6 sm:p-8 shadow-md relative overflow-hidden">
        <div className="absolute right-0 top-0 translate-x-8 -translate-y-8 w-64 h-64 bg-emerald-500/10 rounded-full blur-2xl pointer-events-none" />
        <div className="relative z-10 max-w-2xl space-y-4">
          <div className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ${
            isFastPracticeResuming
              ? "bg-amber-400/20 text-amber-300 border-amber-400/30"
              : "bg-emerald-500/20 text-emerald-300 border-emerald-400/30"
          }`}>
            {isFastPracticeResuming ? (
              <RotateCcw className="w-3.5 h-3.5" />
            ) : (
              <Zap className="w-3.5 h-3.5 fill-emerald-300" />
            )}
            <span>
              {isFastPracticeResuming
                ? (lang === "ky" ? "Машыгуу улантылууда" : "Тренировка в процессе")
                : (lang === "ky" ? "Ылдам машыгуу (25 суроо)" : "Экспресс-тренировка (25 вопросов)")}
            </span>
          </div>

          <h3 className="text-2xl font-extrabold tracking-tight">
            {lang === "ky"
              ? "Экспресс-машыгуу: 25 кокус суроо"
              : "Экспресс-тренировка: 25 случайных вопросов"}
          </h3>

          <p className="text-sm text-emerald-100/90 leading-relaxed">
            {lang === "ky"
              ? "Бардык машыгуу базасынан (Practice Bank) кокустук менен 25 суроо тандалып, реалдуу ОРТ бөлүмдөрүнүн ирети менен берилет."
              : "Динамическая выборка 25 случайных вопросов из базы практики в строгой хронологической последовательности разделов ОРТ."}
          </p>

          <div className="flex flex-wrap items-center gap-6 pt-1 text-xs text-emerald-200">
            <span className="flex items-center gap-1.5 font-semibold">
              <Clock className="w-4 h-4 text-emerald-400" />
              <span>30 {lang === "ky" ? "мүнөт" : "минут"}</span>
            </span>
            <span className="flex items-center gap-1.5 font-semibold">
              <Layers className="w-4 h-4 text-emerald-400" />
              <span>25 {lang === "ky" ? "суроо" : "вопросов"}</span>
            </span>
            <span className="flex items-center gap-1.5 font-semibold">
              <Award className="w-4 h-4 text-emerald-400" />
              <span>60-245 {lang === "ky" ? "балл шкаласы" : "шкала ОРТ"}</span>
            </span>
          </div>

          <div className="pt-2">
            <Link
              href={
                isFastPracticeResuming
                  ? `/${lang}/mock-tests/${fastPracticeInProg?.templateId || fastPracticeId}`
                  : `/${lang}/mock-tests/${fastPracticeId}?force_new=true`
              }
              className={`inline-flex items-center gap-2 px-6 py-3 font-bold rounded-2xl shadow-md transition-all text-sm group ${
                isFastPracticeResuming
                  ? "bg-amber-400 text-slate-950 hover:bg-amber-300"
                  : "bg-white text-emerald-950 hover:bg-emerald-50"
              }`}
            >
              {isFastPracticeResuming ? (
                <>
                  <RotateCcw className="w-4 h-4" />
                  <span>{lang === "ky" ? "Машыгууну улантуу" : "Возобновить экспресс-тренировку"}</span>
                </>
              ) : (
                <>
                  <span>{lang === "ky" ? "Жаңы машыгууну баштоо" : "Начать новую тренировку"}</span>
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </Link>
          </div>
        </div>
      </div>

      {/* ZONE 2: Full Main ORT Tests */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-900">
              {lang === "ky"
                ? "ОРТ Негизги сыноо тесттери (Толук формат)"
                : "Полные пробные тесты ОРТ (Основной тест)"}
            </h3>
            <p className="text-xs text-slate-500">
              {lang === "ky"
                ? "Математика I, II, Окуу жана түшүнүү, Аналогиялар, Грамматика бөлүмдөрү."
                : "Математика I, II, Чтение и понимание, Аналогии, Практическая грамматика."}
            </p>
          </div>
          <span className="px-3 py-1 bg-indigo-50 text-indigo-700 font-bold text-xs rounded-full border border-indigo-200">
            {lang.toUpperCase()}
          </span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center p-10 bg-white rounded-2xl border border-slate-200">
            <div className="flex flex-col items-center gap-2 text-slate-400">
              <RefreshCw className="w-6 h-6 animate-spin text-indigo-600" />
              <span className="text-xs">{t("common.loading")}</span>
            </div>
          </div>
        ) : fullMainExams.length === 0 ? (
          <div className="p-8 text-center bg-white rounded-2xl border border-slate-200">
            <p className="text-sm font-semibold text-slate-600">
              {lang === "ky" ? "Азырынча жарыяланган негизги тесттер жок" : "В данный момент нет опубликованных основных тестов"}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {fullMainExams.map(renderExamCard)}
          </div>
        )}
      </div>

      {/* ZONE 3: Subject Tests */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-900">
              {lang === "ky" ? "Предметтик сыноо тесттери" : "Предметные тесты ОРТ"}
            </h3>
            <p className="text-xs text-slate-500">
              {lang === "ky"
                ? "Химия, Биология, Физика, Тарых жана Англис тили боюнча предметтик тесттер."
                : "Химия, Биология, Физика, История и Английский язык."}
            </p>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1 bg-purple-50 text-purple-700 font-bold text-xs rounded-full border border-purple-200">
            <Compass className="w-3.5 h-3.5" />
            <span>{lang === "ky" ? "Предметтик" : "Предметные"}</span>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center p-10 bg-white rounded-2xl border border-slate-200">
            <div className="flex flex-col items-center gap-2 text-slate-400">
              <RefreshCw className="w-6 h-6 animate-spin text-purple-600" />
              <span className="text-xs">{t("common.loading")}</span>
            </div>
          </div>
        ) : subjectExams.length === 0 ? (
          <div className="p-8 text-center bg-white rounded-2xl border border-slate-200">
            <p className="text-sm font-semibold text-slate-600">
              {lang === "ky"
                ? "Азырынча сизге ачылган предметтик тесттер жок"
                : "В данный момент нет открытых предметных тестов"}
            </p>
            <p className="text-xs text-slate-400 mt-1">
              {lang === "ky"
                ? "Куратор же администратор сизге предметтик тестке уруксат бергенден кийин, ал бул жерде пайда болот."
                : "После того как администратор откроет вам доступ к предметному тесту, он появится здесь."}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {subjectExams.map(renderExamCard)}
          </div>
        )}
      </div>

      {/* 4-digit PIN Modal */}
      {pinModalExam && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-sm p-4">
          <div className="bg-white w-full max-w-sm rounded-2xl shadow-xl border border-slate-200 p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-indigo-600 font-bold text-sm">
                <KeyRound className="w-5 h-5" />
                <span>{lang === "ky" ? "Экзаменге кирүү коду" : "Код доступа к экзамену"}</span>
              </div>
              <button
                onClick={() => setPinModalExam(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-500">
              {lang === "ky"
                ? `«${pinModalExam.title}» экзаменине кирүү үчүн мугалим же куратор берген 4 орундуу PIN-кодду жазыңыз:`
                : `Для доступа к тесту «${pinModalExam.title}» введите 4-значный PIN-код, полученный от преподавателя:`}
            </p>

            <form onSubmit={handleVerifyPinAndStart} className="space-y-4">
              {pinError && (
                <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{pinError}</span>
                </div>
              )}

              <input
                type="text"
                autoFocus
                maxLength={4}
                required
                placeholder="____"
                value={enteredPin}
                onChange={(e) => setEnteredPin(e.target.value)}
                className="w-full text-center text-2xl font-mono tracking-widest py-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 font-bold"
              />

              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setPinModalExam(null)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl"
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl shadow-sm transition"
                >
                  {lang === "ky" ? "Кирүү" : "Войти"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
