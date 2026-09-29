"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { apiClient } from "@/lib/api";
import TargetScoreModal from "@/components/ui/TargetScoreModal";
import {
  TrendingUp,
  Award,
  Target,
  Flame,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  BookOpen,
  Clock,
  BarChart3,
  Calendar,
  Sparkles,
  Edit3,
} from "lucide-react";

interface SectionMastery {
  section: string;
  totalAttempted: number;
  correctCount: number;
  accuracyPercentage: number;
  averageTimePerQuestionSeconds: number;
}

interface TopicWeakSpot {
  topic: string;
  section: string;
  totalAttempted: number;
  accuracyPercentage: number;
  recommendedAction: string;
}

interface RecentScoreItem {
  attemptId?: string;
  date: string;
  scaled: number;
  raw: number;
  percentile?: number;
  templateId?: string;
}

interface StudentAnalyticsResponse {
  userId: string;
  currentEstimatedScore: number;
  targetScore: number;
  scoreGap: number;
  streak: number;
  totalTestsCompleted: number;
  totalQuestionsPracticed: number;
  overallAccuracy: number;
  sectionsMastery: Record<string, SectionMastery>;
  mainSectionsMastery: Record<string, SectionMastery>;
  subjectSectionsMastery: Record<string, SectionMastery>;
  topWeakSpots: TopicWeakSpot[];
  recentScores: RecentScoreItem[];
}

const MAIN_SECTION_KEYS = ["math_1", "math_2", "reading", "analogies", "grammar"];

export default function StudentProgressPage() {
  const { lang, t } = useTranslation();
  const { userProfile, updateTargetScore } = useAuth();

  const [analytics, setAnalytics] = useState<StudentAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [isTargetModalOpen, setIsTargetModalOpen] = useState(false);

  const fetchAnalytics = async () => {
    try {
      const data = await apiClient<StudentAnalyticsResponse>("/analytics/student");
      setAnalytics(data);
    } catch {
      // Graceful fallback for brand-new users with 0 test attempts
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const handleSaveTargetScore = async (newScore: number) => {
    try {
      await updateTargetScore(newScore);
      setAnalytics((prev) =>
        prev
          ? {
              ...prev,
              targetScore: newScore,
              scoreGap: Math.max(0, newScore - prev.currentEstimatedScore),
            }
          : null
      );
    } catch {
      // Error handled inside modal
    }
  };

  const currentScore = analytics?.currentEstimatedScore ?? (userProfile?.currentEstimatedScore || 150);
  const targetScore = analytics?.targetScore || userProfile?.target_score || 200;
  const goldenCertThreshold = 219;
  const pointsToTarget = Math.max(0, targetScore - currentScore);
  const pointsToGold = Math.max(0, goldenCertThreshold - currentScore);
  const streakDays = analytics?.streak ?? userProfile?.streak?.current ?? 0;

  // Calculate score progress from first attempt
  const recentScores = analytics?.recentScores || [];
  const firstScore = recentScores.length > 0 ? recentScores[0].scaled : currentScore;
  const scoreGrowth = currentScore - firstScore;

  // Subject sections that have been attempted
  const subjectSectionsList = Object.entries(analytics?.subjectSectionsMastery || {}).filter(
    ([_, sec]) => sec.totalAttempted > 0
  );

  const topWeakSpot = analytics?.topWeakSpots?.[0];

  return (
    <div className="space-y-8">
      {/* Target Score Modal */}
      <TargetScoreModal
        isOpen={isTargetModalOpen}
        onClose={() => setIsTargetModalOpen(false)}
        initialScore={targetScore}
        onSave={handleSaveTargetScore}
      />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <BarChart3 className="w-7 h-7 text-brand-600" />
            <span>{t("nav.analytics")}</span>
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            {lang === "ky"
              ? "Жеке даярдык жыйынтыктарыңыз, баллдардын динамикасы жана сунуштар."
              : "Ваша личная динамика подготовки к ОРТ, результаты тестов и рекомендации."}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href={`/${lang}/mistakes`}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 text-xs font-semibold hover:bg-slate-50 transition-colors shadow-2xs"
          >
            <BookOpen className="w-4 h-4 text-brand-600" />
            <span>{lang === "ky" ? "Каталар топтому" : "Работа над ошибками"}</span>
          </Link>
          <Link
            href={`/${lang}/mock-tests`}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-600 text-white text-xs font-semibold hover:bg-brand-700 transition-colors shadow-2xs"
          >
            <Clock className="w-4 h-4" />
            <span>{lang === "ky" ? "Жаңы тест баштоо" : "Начать новый тест"}</span>
          </Link>
        </div>
      </div>

      {/* KPI Overview Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Current Score */}
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500">
              {lang === "ky" ? "Учурдагы балл" : "Текущий балл ОРТ"}
            </span>
            <div className="w-8 h-8 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-black text-brand-600">
              {loading ? "..." : currentScore}
            </span>
            {recentScores.length > 1 && scoreGrowth !== 0 && (
              <span
                className={`text-xs font-bold ${
                  scoreGrowth > 0 ? "text-emerald-600" : "text-rose-600"
                }`}
              >
                {scoreGrowth > 0 ? `+${scoreGrowth}` : scoreGrowth} {lang === "ky" ? "балл" : "баллов"}
              </span>
            )}
          </div>
          <span className="text-[11px] text-slate-400 mt-1 block">
            {recentScores.length > 0
              ? `${lang === "ky" ? "Жалпы тапшырылган тесттер:" : "Всего пройдено тестов:"} ${recentScores.length}`
              : (lang === "ky" ? "Диагностикалык балл" : "Диагностический балл")}
          </span>
        </div>

        {/* Target Score (Interactive) */}
        <button
          onClick={() => setIsTargetModalOpen(true)}
          className="bg-white p-5 rounded-2xl border border-slate-200 hover:border-emerald-300 hover:shadow-md transition-all text-left group shadow-2xs"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500 group-hover:text-emerald-700 transition-colors">
              {lang === "ky" ? "Максаттуу балл" : "Целевой балл"}
            </span>
            <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center group-hover:bg-emerald-600 group-hover:text-white transition-colors">
              <Target className="w-4 h-4" />
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-black text-slate-900 group-hover:text-emerald-600 transition-colors">
              {targetScore}
            </span>
            <span className="text-xs text-amber-600 font-bold">
              {pointsToTarget === 0
                ? (lang === "ky" ? "Жеттиңиз! 🎉" : "Достигнут! 🎉")
                : `-${pointsToTarget} ${lang === "ky" ? "балл калды" : "осталось"}`}
            </span>
          </div>
          <div className="flex items-center justify-between mt-1">
            <span className="text-[11px] text-slate-400">
              {targetScore >= 219
                ? (lang === "ky" ? "Алтын сертификат деңгээли" : "Уровень Золотого сертификата")
                : targetScore >= 175
                ? (lang === "ky" ? "Бюджеттик грант максаты" : "Цель на бюджетный грант")
                : (lang === "ky" ? "Контракттык босого" : "Контрактный порог")}
            </span>
            <span className="text-[10px] text-emerald-600 font-semibold opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5">
              <Edit3 className="w-3 h-3" />
              {lang === "ky" ? "Өзгөртүү" : "Изменить"}
            </span>
          </div>
        </button>

        {/* Golden Certificate */}
        <div className="bg-white p-5 rounded-2xl border border-amber-200/80 bg-gradient-to-br from-white to-amber-50/30 shadow-2xs">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-amber-800">
              {lang === "ky" ? "Алтын сертификат" : "Золотой сертификат"}
            </span>
            <div className="w-8 h-8 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center">
              <Award className="w-4 h-4" />
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-black text-amber-600">{goldenCertThreshold}+</span>
            <span className="text-xs text-slate-500 font-medium">
              {pointsToGold === 0
                ? (lang === "ky" ? "Куттуктайбыз! 🏆" : "Поздравляем! 🏆")
                : `-${pointsToGold} ${lang === "ky" ? "балл" : "баллов"}`}
            </span>
          </div>
          <span className="text-[11px] text-amber-700/80 mt-1 block font-medium">
            {lang === "ky" ? "Эң мыкты 50 окуучу катарына" : "Топ-50 абитуриентов страны"}
          </span>
        </div>

        {/* Streak */}
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500">
              {lang === "ky" ? "Стрик режими" : "Ударный режим"}
            </span>
            <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
              <Flame className="w-4 h-4 fill-amber-500 text-amber-500" />
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-black text-slate-900">{streakDays}</span>
            <span className="text-xs text-amber-600 font-bold">
              {lang === "ky" ? "күн катары менен" : "дней подряд"}
            </span>
          </div>
          <span className="text-[11px] text-slate-400 mt-1 block">
            {lang === "ky" ? "Максат: 30 күндүк стрик" : "Цель: 30 дней подряд"}
          </span>
        </div>
      </div>

      {/* Main Section Mastery (ОРТ Негизги тест) */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-100 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-brand-50 text-brand-700 border border-brand-200">
                {lang === "ky" ? "Милдеттүү бөлүктөр" : "Обязательные части"}
              </span>
              <h3 className="text-lg font-bold text-slate-900">
                {lang === "ky" ? "ОРТ Негизги тест (5 бөлүм)" : "Основной тест ОРТ (5 разделов)"}
              </h3>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {lang === "ky"
                ? "Математика I, II, Окуу жана түшүнүү, Аналогиялар жана Грамматика боюнча өздөштүрүү деңгээли."
                : "Уровень усвоения по Математике I, II, Чтению, Аналогиям и Практической грамматике."}
            </p>
          </div>
          {analytics && (
            <div className="text-xs font-semibold text-slate-600">
              {lang === "ky" ? "Жалпы тактык:" : "Общая точность:"}{" "}
              <span className="text-brand-600 font-bold text-sm">
                {analytics.overallAccuracy}%
              </span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {MAIN_SECTION_KEYS.map((secKey) => {
            const mastery = analytics?.mainSectionsMastery?.[secKey];
            const accuracy = mastery?.accuracyPercentage ?? 0;
            const attempted = mastery?.totalAttempted ?? 0;
            const correct = mastery?.correctCount ?? 0;
            const sectionName = t(`sections.${secKey}`) || secKey;

            return (
              <div
                key={secKey}
                className="p-4 rounded-xl border border-slate-100 bg-slate-50/50 space-y-2.5"
              >
                <div className="flex justify-between items-center text-xs">
                  <span className="font-semibold text-slate-800">{sectionName}</span>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-slate-900">{accuracy}%</span>
                    <span className="text-slate-400 text-[11px]">
                      ({correct} / {attempted} {lang === "ky" ? "туура" : "верно"})
                    </span>
                  </div>
                </div>

                <div className="w-full bg-slate-200/80 rounded-full h-2.5 overflow-hidden">
                  <div
                    className={`h-2.5 rounded-full transition-all duration-500 ${
                      accuracy >= 75
                        ? "bg-brand-600"
                        : accuracy >= 50
                        ? "bg-amber-500"
                        : attempted === 0
                        ? "bg-slate-300"
                        : "bg-rose-500"
                    }`}
                    style={{ width: `${attempted === 0 ? 5 : accuracy}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Subject Tests Panel (Предметтик тесттер) */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-100 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                {lang === "ky" ? "Кошумча предметтер" : "Предметные тесты"}
              </span>
              <h3 className="text-lg font-bold text-slate-900">
                {lang === "ky" ? "Предметтик тесттер" : "Предметные тесты"}
              </h3>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {lang === "ky"
                ? "Сиз тапшырган предметтик тесттер боюнча жеке өздөштүрүү көрсөткүчү."
                : "Индивидуальные показатели по сданным предметным тестам."}
            </p>
          </div>
        </div>

        {subjectSectionsList.length === 0 ? (
          <div className="p-8 rounded-2xl bg-slate-50 border border-dashed border-slate-200 text-center space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-indigo-50 text-indigo-600 mx-auto flex items-center justify-center">
              <Sparkles className="w-6 h-6" />
            </div>
            <div className="max-w-md mx-auto">
              <h4 className="text-sm font-bold text-slate-800">
                {lang === "ky"
                  ? "Предметтик тесттер тапшырыла элек"
                  : "Предметные тесты еще не пройдены"}
              </h4>
              <p className="text-xs text-slate-500 mt-1">
                {lang === "ky"
                  ? "Химия, Биология, Физика, Тарых же Англис тили боюнча билимиңизди сынап көрүңүз."
                  : "Проверьте свои знания по химии, биологии, физике, истории или английскому языку."}
              </p>
            </div>
            <Link
              href={`/${lang}/mock-tests`}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 transition-colors shadow-2xs"
            >
              <span>{lang === "ky" ? "Предметтик тестти тандоо" : "Выбрать предметный тест"}</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {subjectSectionsList.map(([secKey, mastery]) => {
              const accuracy = mastery.accuracyPercentage;
              const sectionName = t(`sections.${secKey}`) || secKey;

              return (
                <div
                  key={secKey}
                  className="p-4 rounded-xl border border-slate-100 bg-slate-50/50 space-y-2.5"
                >
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-semibold text-slate-800">{sectionName}</span>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-900">{accuracy}%</span>
                      <span className="text-slate-400 text-[11px]">
                        ({mastery.correctCount} / {mastery.totalAttempted} {lang === "ky" ? "туура" : "верно"})
                      </span>
                    </div>
                  </div>

                  <div className="w-full bg-slate-200/80 rounded-full h-2.5 overflow-hidden">
                    <div
                      className={`h-2.5 rounded-full transition-all duration-500 ${
                        accuracy >= 75
                          ? "bg-indigo-600"
                          : accuracy >= 50
                          ? "bg-amber-500"
                          : "bg-rose-500"
                      }`}
                      style={{ width: `${accuracy}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Dynamic Recommendation Box */}
        {topWeakSpot && (
          <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
            <div className="text-xs text-amber-900 space-y-1">
              <span className="font-bold block">
                {lang === "ky" ? "Көңүл буруу керек болгон багыт:" : "Рекомендация по приоритету:"}
              </span>
              <p>
                {topWeakSpot.topic}: {topWeakSpot.recommendedAction}.{" "}
                <Link
                  href={`/${lang}/mistakes`}
                  className="underline font-semibold hover:text-amber-950 ml-1"
                >
                  {lang === "ky" ? "Каталар топтомун ачуу →" : "Открыть работу над ошибками →"}
                </Link>
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Score Progression History */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-900">
              {lang === "ky" ? "Баллдардын өсүү траекториясы" : "Динамика роста баллов ОРТ"}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              {lang === "ky"
                ? "Бардык тапшырылган сыноо тесттеринин хронологиясы"
                : "Хронология всех попыток тестирования"}
            </p>
          </div>
          <Link
            href={`/${lang}/mock-tests`}
            className="hidden sm:inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-700"
          >
            <span>{lang === "ky" ? "Жаңы тест тапшыруу" : "Пройти тест"}</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {recentScores.length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-xs space-y-3">
            <p>
              {lang === "ky"
                ? "Азырынча тапшырылган тесттердин тарыхы жок."
                : "У вас пока нет завершенных пробных тестов."}
            </p>
            <Link
              href={`/${lang}/mock-tests`}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-600 text-white font-semibold hover:bg-brand-700 transition-colors shadow-2xs"
            >
              <span>{lang === "ky" ? "Биринчи тестти баштоо" : "Начать первый тест"}</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {[...recentScores].reverse().map((item, idx) => (
              <div
                key={item.attemptId || idx}
                className="flex items-center justify-between p-4 rounded-xl border border-slate-100 hover:border-slate-200 bg-white transition-all shadow-2xs"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-900 text-sm">
                      {lang === "ky" ? "ЖРТ Сыноо тести" : "Пробный тест ОРТ"}
                    </span>
                    {item.scaled >= 219 && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                        {lang === "ky" ? "Алтын Сертификат" : "Золотой Сертификат"}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-400">
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3.5 h-3.5" />
                      {item.date}
                    </span>
                    <span>•</span>
                    <span>
                      {item.raw} {lang === "ky" ? "балл туура" : "баллов"}
                    </span>
                  </div>
                </div>

                <div className="text-right">
                  <span className="text-xl font-black text-brand-600 block">
                    {item.scaled}
                  </span>
                  {item.percentile !== undefined && (
                    <span className="text-xs text-emerald-600 font-semibold">
                      {item.percentile}% {lang === "ky" ? "перцентиль" : "перцентиль"}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="pt-2 sm:hidden">
          <Link
            href={`/${lang}/mock-tests`}
            className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-slate-900 text-white font-semibold text-xs hover:bg-slate-800 transition-colors"
          >
            <span>{lang === "ky" ? "Жаңы сыноо тестин тапшыруу" : "Пройти следующий пробный тест"}</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </div>
  );
}
