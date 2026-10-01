"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { Users, Award, TrendingUp, BarChart2, RefreshCw, AlertCircle, HelpCircle } from "lucide-react";
import { apiClient } from "@/lib/api";

interface QuestionDiscriminationStat {
  questionId: string;
  section: string;
  topic: string;
  totalAttempts: number;
  accuracyRate: number;
  discriminationIndex: number;
  flaggedHard: boolean;
}

interface InstructorAnalyticsResponse {
  totalStudents: number;
  totalTestsTaken: number;
  averageScaledScore: number;
  goldenCertificateEligibleCount: number;
  scoreDistribution: Record<string, number>;
  hardestQuestions: QuestionDiscriminationStat[];
}

const SCORE_RANGES = [
  { key: "<110", rangeLabel: "< 110", ky: "Босогодон төмөн", ru: "Ниже порогового", color: "bg-rose-400" },
  { key: "110-140", rangeLabel: "110 - 140", ky: "Базалык деңгээл", ru: "Базовый уровень", color: "bg-amber-400" },
  { key: "140-175", rangeLabel: "140 - 175", ky: "Орточо деңгээл", ru: "Средний уровень", color: "bg-indigo-500" },
  { key: "175-200", rangeLabel: "175 - 200", ky: "Жогорку деңгээл", ru: "Высокий уровень", color: "bg-indigo-600" },
  { key: "200-218", rangeLabel: "200 - 218", ky: "Мыкты деңгээл", ru: "Отличный уровень", color: "bg-emerald-500" },
  { key: "219+", rangeLabel: "219+", ky: "Алтын сертификат", ru: "Золотой сертификат", color: "bg-amber-500" },
];

export default function InstructorAnalyticsPage() {
  const { lang, t } = useTranslation();
  const [data, setData] = useState<InstructorAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAnalytics = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient<InstructorAnalyticsResponse>("/analytics/instructor");
      setData(res);
    } catch (err: any) {
      setError(err?.message || (lang === "ky" ? "Маалымат жүктөөдө ката кетти" : "Ошибка загрузки данных"));
    } finally {
      setLoading(false);
    }
  }, [lang]);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  const totalTests = data?.totalTestsTaken ?? 0;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight">
            {t("nav.admin.studentAnalytics")}
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            {lang === "ky"
              ? "Окуучулардын баллдык бөлүштүрүлүшү, Алтын сертификатка талапкерлер жана эң татаал суроолор боюнча аналитика."
              : "Когортная аналитика распределения баллов, кандидаты на Золотой сертификат и анализ дискриминативности вопросов."}
          </p>
        </div>

        <button
          onClick={fetchAnalytics}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 text-xs font-semibold hover:bg-slate-50 disabled:opacity-50 transition-colors shadow-2xs self-start sm:self-auto"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-brand-600" : ""}`} />
          <span>{lang === "ky" ? "Жаңылоо" : "Обновить"}</span>
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 flex items-center gap-3 text-rose-800 text-xs">
          <AlertCircle className="w-5 h-5 flex-shrink-0 text-rose-600" />
          <span>{error}</span>
        </div>
      )}

      {/* Cohort KPI Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <Link
          href={`/${lang}/students`}
          className="bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs hover:border-indigo-400 hover:shadow-md transition-all cursor-pointer group"
        >
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white transition-colors flex items-center justify-center font-bold">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <span className="text-xs text-slate-400 font-medium block group-hover:text-indigo-600 transition-colors">
                {lang === "ky" ? "Окуучулар саны →" : "Количество учеников →"}
              </span>
              <span className="text-2xl font-extrabold text-slate-900">
                {loading ? "..." : (data?.totalStudents ?? 0)}
              </span>
            </div>
          </div>
        </Link>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold">
              <TrendingUp className="w-5 h-5" />
            </div>
            <div>
              <span className="text-xs text-slate-400 font-medium block">
                {lang === "ky" ? "Орточо ОРТ балл" : "Средний балл ОРТ"}
              </span>
              <span className="text-2xl font-extrabold text-emerald-600">
                {loading ? "..." : (data?.averageScaledScore ? data.averageScaledScore.toFixed(1) : "0.0")}
              </span>
            </div>
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center font-bold">
              <Award className="w-5 h-5" />
            </div>
            <div>
              <span className="text-xs text-slate-400 font-medium block">
                {lang === "ky" ? "Алтын Сертификат (219+)" : "Золотой Сертификат (219+)"}
              </span>
              <span className="text-2xl font-extrabold text-amber-600">
                {loading ? "..." : (data?.goldenCertificateEligibleCount ?? 0)}
              </span>
            </div>
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-slate-100 text-slate-700 flex items-center justify-center font-bold">
              <BarChart2 className="w-5 h-5" />
            </div>
            <div>
              <span className="text-xs text-slate-400 font-medium block">
                {lang === "ky" ? "Жалпы сыноо тесттери" : "Всего пробных тестов"}
              </span>
              <span className="text-2xl font-extrabold text-slate-900">
                {loading ? "..." : totalTests}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Score Distribution Chart */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs space-y-6">
        <div>
          <h3 className="text-lg font-bold text-slate-900">
            {lang === "ky" ? "ОРТ Баллдарынын Бөлүштүрүлүшү" : "Распределение баллов ОРТ"}
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {lang === "ky" ? "Нормативдик шкала (60 - 245 балл)" : "Нормативная шкала (60 - 245 баллов)"}
          </p>
        </div>

        <div className="space-y-4">
          {SCORE_RANGES.map((item) => {
            const count = data?.scoreDistribution?.[item.key] ?? 0;
            const pct = totalTests > 0 ? Number(((count / totalTests) * 100).toFixed(1)) : 0;
            const barWidth = pct > 0 ? Math.min(100, Math.max(2, pct)) : 0;

            return (
              <div key={item.key} className="space-y-1.5">
                <div className="flex justify-between text-xs font-semibold text-slate-700">
                  <span className="w-24 font-mono">{item.rangeLabel}</span>
                  <span className="text-slate-500 text-right flex-1 pr-4">
                    {lang === "ky" ? item.ky : item.ru}
                  </span>
                  <span className="w-28 text-right font-bold text-slate-900">
                    {count} {lang === "ky" ? "тест" : "тестов"} ({pct}%)
                  </span>
                </div>
                <div className="w-full bg-slate-100 rounded-full h-3 overflow-hidden">
                  <div
                    className={`h-3 rounded-full transition-all duration-500 ${item.color}`}
                    style={{ width: `${barWidth}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Hardest Questions & Discrimination Index */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs space-y-4">
        <div>
          <h3 className="text-lg font-bold text-slate-900">
            {lang === "ky" ? "Эң Татаал Суроолор (Анализ)" : "Наиболее сложные вопросы"}
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {lang === "ky"
              ? "Дискриминативдик индекс (D ≥ 0.40 суроо күчтүү жана начар окуучуларды жакшы айырмалайт)"
              : "Индекс дискриминативности (D ≥ 0.40 хорошо дифференцирует сильных и слабых учеников)"}
          </p>
        </div>

        {(!data?.hardestQuestions || data.hardestQuestions.length === 0) ? (
          <div className="py-12 text-center text-slate-400 text-xs">
            {lang === "ky"
              ? "Азырынча суроолор боюнча тест тапшыруу тарыхы жок."
              : "Пока нет данных о попытках прохождения вопросов."}
          </div>
        ) : (
          <div className="rounded-2xl border border-slate-200 overflow-hidden">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 uppercase text-[11px] border-b border-slate-200">
                <tr>
                  <th className="px-5 py-3">{lang === "ky" ? "Суроо ID" : "ID вопроса"}</th>
                  <th className="px-5 py-3">{lang === "ky" ? "Бөлүм / Тема" : "Раздел / Тема"}</th>
                  <th className="px-5 py-3">{lang === "ky" ? "Аракеттер" : "Попытки"}</th>
                  <th className="px-5 py-3">{lang === "ky" ? "Тактык %" : "Точность %"}</th>
                  <th className="px-5 py-3">{lang === "ky" ? "Индекс (D)" : "Индекс (D)"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.hardestQuestions.map((q) => {
                  const sectionTranslated = t(`sections.${q.section}`) || q.section;
                  return (
                    <tr key={q.questionId} className="hover:bg-slate-50/70 transition-colors">
                      <td className="px-5 py-3.5 font-mono font-bold text-brand-700">
                        {q.questionId}
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="font-semibold text-slate-900 block">{sectionTranslated}</span>
                        <span className="text-[11px] text-slate-500">{q.topic}</span>
                      </td>
                      <td className="px-5 py-3.5 text-slate-600">{q.totalAttempts}</td>
                      <td className="px-5 py-3.5 font-bold text-rose-600">{q.accuracyRate}%</td>
                      <td className="px-5 py-3.5 font-bold text-emerald-700">{q.discriminationIndex}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
