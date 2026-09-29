"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { apiClient } from "@/lib/api";
import { DailyPlannerWidget } from "@/components/planner/DailyPlannerWidget";
import { TargetScoreWidget } from "@/components/planner/TargetScoreWidget";
import { Clock, Play, ArrowRight, History, Award, BookOpen, ChevronRight } from "lucide-react";

interface RecentScoreItem {
  attemptId?: string;
  date: string;
  scaled: number;
  raw: number | string;
  percentile?: number;
  templateId?: string;
}

interface StudentAnalytics {
  userId: string;
  currentEstimatedScore: number;
  targetScore: number;
  scoreGap: number;
  totalTestsCompleted: number;
  recentScores: RecentScoreItem[];
}

interface ExamSetSummary {
  id: string;
  title: string;
  exam_type?: string;
  time_limit_minutes?: number | null;
  totalTimeMinutes?: number;
  totalQuestions?: number;
  question_count?: number;
}

export default function StudentDashboardPage() {
  const { lang, t } = useTranslation();
  const { userProfile } = useAuth();

  const [recentTests, setRecentTests] = useState<RecentScoreItem[]>([]);
  const [availableExams, setAvailableExams] = useState<ExamSetSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const studentName =
    userProfile?.displayName || (lang === "ky" ? "Айбек" : "Айбек");

  useEffect(() => {
    let isMounted = true;
    async function fetchDashboardData() {
      try {
        const [analyticsRes, examsRes] = await Promise.allSettled([
          apiClient<StudentAnalytics>("/analytics/student"),
          apiClient<ExamSetSummary[]>(`/exam-sets/student?lang=${lang}`),
        ]);

        if (!isMounted) return;

        if (analyticsRes.status === "fulfilled" && analyticsRes.value) {
          const data = analyticsRes.value;
          if (data.recentScores && data.recentScores.length > 0) {
            setRecentTests([...data.recentScores].reverse());
          }
        }

        if (examsRes.status === "fulfilled" && Array.isArray(examsRes.value)) {
          setAvailableExams(examsRes.value);
        }
      } catch {
        // Fallback or keep empty
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }
    fetchDashboardData();
    return () => {
      isMounted = false;
    };
  }, [lang]);

  const fullMainExam = availableExams.find(
    (e) => e.exam_type === "full_main" || (!e.exam_type && !e.id.includes("subject") && !e.id.includes("practice"))
  ) || availableExams[0];
  const mainTimeMinutes = fullMainExam?.time_limit_minutes !== undefined ? fullMainExam?.time_limit_minutes : (fullMainExam?.totalTimeMinutes ?? 170);
  const mainTimeDisplay = mainTimeMinutes != null
    ? `${mainTimeMinutes} ${lang === "ky" ? "мүнөт" : "минут"}`
    : (lang === "ky" ? "Чектөөсүз" : "Без ограничений");
  const mainQuestionsCount = fullMainExam?.question_count ?? fullMainExam?.totalQuestions ?? 150;

  const speedDrillExam = availableExams.find(
    (e) => e.exam_type === "practice_bank" || e.id.includes("practice") || e.id.includes("speed")
  );
  const speedDrillTimeMinutes = speedDrillExam?.time_limit_minutes !== undefined ? speedDrillExam?.time_limit_minutes : 30;
  const speedDrillTimeDisplay = speedDrillTimeMinutes != null
    ? `${speedDrillTimeMinutes} ${lang === "ky" ? "мүнөт" : "минут"}`
    : (lang === "ky" ? "Чектөөсүз" : "Без ограничений");

  return (
    <div className="space-y-8">
      {/* Banner */}
      <div className="rounded-3xl bg-gradient-to-r from-indigo-700 via-indigo-800 to-slate-900 p-8 text-white shadow-md relative overflow-hidden">
        <div className="relative z-10 max-w-2xl space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 backdrop-blur-xs border border-white/20 text-xs font-semibold">
            <Award className="w-3.5 h-3.5 text-amber-300" />
            <span>ЖРТ 2026 Даярдык</span>
          </div>

          <h2 className="text-3xl font-extrabold tracking-tight">
            {lang === "ky"
              ? `${studentName}, кайрадан кош келиңиз!`
              : `${studentName}, добро пожаловать снова!`}
          </h2>

          <p className="text-indigo-100 text-sm leading-relaxed">
            {lang === "ky"
              ? "Бүгүнкү күнгө окуу тапшырмалары даяр. Максатыңыз — Алтын сертификат (219+ балл). Стрикти үзбөй улантыңыз!"
              : "На сегодня запланированы задачи. Ваша цель — Золотой сертификат (219+ баллов). Сохраняйте ударный темп!"}
          </p>

          <div className="pt-2 flex flex-wrap gap-3">
            <Link
              href={`/${lang}/mock-tests`}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white text-indigo-800 font-bold text-xs shadow-xs hover:bg-indigo-50 transition-colors"
            >
              <Play className="w-4 h-4 fill-current" />
              <span>{lang === "ky" ? "Сыноо тестин баштоо" : "Начать пробный тест"}</span>
            </Link>

            <Link
              href={`/${lang}/practice`}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-500/30 text-white border border-white/20 font-semibold text-xs hover:bg-indigo-500/40 transition-colors"
            >
              <span>{lang === "ky" ? "Бөлүмдөр боюнча машыгуу" : "Тренировка по темам"}</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>

      {/* Two Column Layout: Daily Planner & Target Score Tracker */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <DailyPlannerWidget />
        <TargetScoreWidget />
      </div>

      {/* Available Exam Templates Quick Card */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-indigo-600" />
            <h3 className="font-bold text-slate-900 text-lg">
              {lang === "ky" ? "ЖРТ Сыноо Тесттери" : "Пробные Тесты ОРТ"}
            </h3>
          </div>
          <Link
            href={`/${lang}/mock-tests`}
            className="text-xs text-indigo-600 font-semibold hover:underline inline-flex items-center gap-1"
          >
            <span>{lang === "ky" ? "Баарын көрүү" : "Посмотреть все"}</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Speed Drill Card */}
          <div className="p-5 rounded-2xl border border-slate-200 bg-slate-50/50 hover:border-indigo-400 hover:bg-white transition-all space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800">
                {lang === "ky" ? "Ылдам спринт" : "Экспресс-спринт"}
              </span>
              <span className="text-xs text-slate-500 font-medium">⏱️ {speedDrillTimeDisplay}</span>
            </div>
            <div>
              <h4 className="font-bold text-slate-900 text-base">
                {lang === "ky" ? "Ылдам машыгуу (25 суроо)" : "Экспресс-тренировка (25 вопросов)"}
              </h4>
              <p className="text-xs text-slate-500 mt-1">
                {lang === "ky"
                  ? "5 бөлүмдүн ар биринен 5тен суроо. Тез арада өзүңүздү текшерүү үчүн идеалдуу."
                  : "По 5 вопросов из каждого раздела. Идеально для быстрой проверки знаний."}
              </p>
            </div>
            <Link
              href={`/${lang}/mock-tests`}
              className="inline-flex items-center justify-center w-full py-2 px-3 rounded-xl bg-indigo-600 text-white font-semibold text-xs hover:bg-indigo-700 transition-colors"
            >
              {lang === "ky" ? "Тестти баштоо" : "Начать тест"}
            </Link>
          </div>

          {/* Full Standard ORT Test */}
          <div className="p-5 rounded-2xl border border-slate-200 bg-slate-50/50 hover:border-indigo-400 hover:bg-white transition-all space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-indigo-100 text-indigo-800">
                {lang === "ky" ? "Толук формат" : "Полный формат"}
              </span>
              <span className="text-xs text-slate-500 font-medium">⏱️ {mainTimeDisplay}</span>
            </div>
            <div>
              <h4 className="font-bold text-slate-900 text-base">
                {fullMainExam?.title || (lang === "ky" ? `ОРТ Негизги тест (${mainQuestionsCount} суроо)` : `ОРТ Основной тест (${mainQuestionsCount} вопросов)`)}
              </h4>
              <p className="text-xs text-slate-500 mt-1">
                {lang === "ky"
                  ? "Реалдуу сынак шарттары: Математика I & II, Окуу, Грамматика, Аналогиялар."
                  : "Реальные условия: Математика I и II, Чтение, Грамматика, Аналогии."}
              </p>
            </div>
            <Link
              href={`/${lang}/mock-tests`}
              className="inline-flex items-center justify-center w-full py-2 px-3 rounded-xl bg-slate-900 text-white font-semibold text-xs hover:bg-slate-800 transition-colors"
            >
              {lang === "ky" ? "Толук тестти баштоо" : "Начать полный экзамен"}
            </Link>
          </div>
        </div>
      </div>

      {/* Recent Test Attempts History */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs">
        <div className="flex items-center gap-2 mb-4">
          <History className="w-5 h-5 text-slate-600" />
          <h3 className="font-bold text-slate-900 text-lg">
            {lang === "ky" ? "Акыркы Тесттердин Жыйынтыгы" : "Результаты Последних Тестов"}
          </h3>
        </div>

        {recentTests.length === 0 ? (
          <div className="p-8 text-center bg-slate-50 rounded-2xl border border-slate-200/80 space-y-3">
            <BookOpen className="w-8 h-8 mx-auto text-slate-400" />
            <p className="text-xs font-semibold text-slate-600">
              {lang === "ky"
                ? "Азырынча тапшырылган тесттер жок"
                : "У вас пока нет завершенных тестов"}
            </p>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              {lang === "ky"
                ? "Биринчи сынамык тестиңизди тапшырып, реалдуу упайыңызды жана талдоону көрүңүз!"
                : "Пройдите первый пробный тест, чтобы увидеть свой реальный балл и анализ знаний!"}
            </p>
            <Link
              href={`/${lang}/mock-tests`}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-bold hover:bg-indigo-700 transition-colors"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{lang === "ky" ? "Тестти баштоо" : "Пройти первый тест"}</span>
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[11px] text-slate-400 uppercase bg-slate-50 border-y border-slate-100">
                <tr>
                  <th className="px-4 py-3">{lang === "ky" ? "Тест" : "Тест"}</th>
                  <th className="px-4 py-3">{lang === "ky" ? "Дата" : "Дата"}</th>
                  <th className="px-4 py-3">{lang === "ky" ? "Туура жооптор" : "Правильно"}</th>
                  <th className="px-4 py-3">{lang === "ky" ? "ОРТ Баллы" : "Балл ОРТ"}</th>
                  <th className="px-4 py-3">{lang === "ky" ? "Перцентиль" : "Перцентиль"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {recentTests.map((t, idx) => (
                  <tr key={t.attemptId || idx} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-4 py-3 font-semibold text-slate-900">
                      {t.templateId?.includes("practice") || t.templateId?.includes("speed_drill")
                        ? lang === "ky"
                          ? "Ылдам машыгуу (25 суроо)"
                          : "Экспресс-тренировка (25 вопросов)"
                        : lang === "ky"
                        ? "ОРТ Негизги тест"
                        : "ОРТ Основной тест"}
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs font-mono">{t.date}</td>
                    <td className="px-4 py-3 text-slate-600">{t.raw}</td>
                    <td className="px-4 py-3">
                      <span className="font-bold text-indigo-600 text-base">{t.scaled}</span>
                    </td>
                    <td className="px-4 py-3 text-emerald-600 font-semibold">
                      {t.percentile ? `${t.percentile}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
