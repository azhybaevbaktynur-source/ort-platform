"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { apiClient } from "@/lib/api";
import { Award, TrendingUp, Loader2 } from "lucide-react";

interface SectionMastery {
  section: string;
  totalAttempted: number;
  correctCount: number;
  accuracyPercentage: number;
  averageTimePerQuestionSeconds: number;
}

interface StudentAnalytics {
  userId: string;
  currentEstimatedScore: number;
  targetScore: number;
  scoreGap: number;
  totalTestsCompleted: number;
  totalQuestionsPracticed: number;
  overallAccuracy: number;
  sectionsMastery: Record<string, SectionMastery>;
  recentScores: Array<{ date: string; scaled: number; raw: number }>;
}

interface UserProfileResponse {
  id: string;
  displayName: string;
  currentEstimatedScore: number;
  targetScore: {
    overall: number;
    math: number;
    reading: number;
    grammar: number;
    analogies: number;
  };
}

export const TargetScoreWidget: React.FC = () => {
  const { lang, t } = useTranslation();

  const [isLoading, setIsLoading] = useState(true);
  const [currentScore, setCurrentScore] = useState(150);
  const [targetScore, setTargetScore] = useState(200);
  const [gap, setGap] = useState(50);
  const [sectionData, setSectionData] = useState<
    Array<{ nameKy: string; nameRu: string; current: number; target: number; max: number }>
  >([
    { nameKy: "Математика I", nameRu: "Математика I", current: 0, target: 50, max: 60 },
    { nameKy: "Окуу жана түшүнүү", nameRu: "Чтение и понимание", current: 0, target: 25, max: 30 },
    { nameKy: "Аналогиялар", nameRu: "Аналогии", current: 0, target: 25, max: 30 },
    { nameKy: "Грамматика", nameRu: "Грамматика", current: 0, target: 25, max: 30 },
  ]);

  useEffect(() => {
    let isMounted = true;

    async function loadData() {
      try {
        const [analytics, profile] = await Promise.allSettled([
          apiClient<StudentAnalytics>("/analytics/student"),
          apiClient<UserProfileResponse>("/auth/me"),
        ]);

        if (!isMounted) return;

        let cur = 150;
        let tgt = 200;
        let mastery: Record<string, SectionMastery> = {};
        let tgtBreakdown = { math: 50, reading: 25, grammar: 25, analogies: 25 };

        if (profile.status === "fulfilled" && profile.value) {
          cur = profile.value.currentEstimatedScore || cur;
          tgt = profile.value.targetScore?.overall || tgt;
          if (profile.value.targetScore) {
            tgtBreakdown = {
              math: profile.value.targetScore.math || 50,
              reading: profile.value.targetScore.reading || 25,
              grammar: profile.value.targetScore.grammar || 25,
              analogies: profile.value.targetScore.analogies || 25,
            };
          }
        }

        if (analytics.status === "fulfilled" && analytics.value) {
          cur = analytics.value.currentEstimatedScore || cur;
          tgt = analytics.value.targetScore || tgt;
          mastery = analytics.value.sectionsMastery || {};
        }

        setCurrentScore(cur);
        setTargetScore(tgt);
        setGap(Math.max(0, tgt - cur));

        setSectionData([
          {
            nameKy: "Математика I",
            nameRu: "Математика I",
            current: mastery["math_1"]?.correctCount || 0,
            target: tgtBreakdown.math,
            max: 60,
          },
          {
            nameKy: "Окуу жана түшүнүү",
            nameRu: "Чтение и понимание",
            current: mastery["reading"]?.correctCount || 0,
            target: tgtBreakdown.reading,
            max: 30,
          },
          {
            nameKy: "Аналогиялар",
            nameRu: "Аналогии",
            current: mastery["analogies"]?.correctCount || 0,
            target: tgtBreakdown.analogies,
            max: 30,
          },
          {
            nameKy: "Практикалык грамматика",
            nameRu: "Практическая грамматика",
            current: mastery["grammar"]?.correctCount || 0,
            target: tgtBreakdown.grammar,
            max: 30,
          },
        ]);
      } catch {
        // Fallback default numbers if offline
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    loadData();
    return () => {
      isMounted = false;
    };
  }, []);

  const isGolden = currentScore >= 219;

  return (
    <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs flex flex-col justify-between">
      <div>
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="font-bold text-slate-900 text-lg">
              {lang === "ky" ? "Максаттуу Балл Трекери" : "Трекер Целевого Балла"}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              {lang === "ky"
                ? "Жалпы республикалык тестирлөө рейтинги"
                : "Рейтинг Общереспубликанского тестирования"}
            </p>
          </div>

          <div
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-bold shadow-xs ${
              isGolden
                ? "bg-amber-100 border-amber-400 text-amber-900 ring-2 ring-amber-300"
                : "bg-amber-50 border-amber-200 text-amber-800"
            }`}
          >
            <Award className="w-4 h-4 text-amber-600" />
            <span>
              {isGolden
                ? lang === "ky"
                  ? "Алтын Сертификат! (219+)"
                  : "Золотой Сертификат! (219+)"
                : lang === "ky"
                ? "Алтын Сертификат (219+)"
                : "Золотой Сертификат (219+)"}
            </span>
          </div>
        </div>

        {/* Main Score Comparison Card */}
        {isLoading ? (
          <div className="flex items-center justify-center p-8 text-slate-400">
            <Loader2 className="w-6 h-6 animate-spin text-indigo-600" />
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between p-4 rounded-2xl bg-slate-50 border border-slate-100 mb-5 text-center divide-x divide-slate-200">
              <div className="flex-1 px-2">
                <span className="text-[11px] text-slate-500 block font-medium mb-1">
                  {lang === "ky" ? "Баштапкы" : "Базовый"}
                </span>
                <span className="text-3xl font-bold text-slate-700 tracking-tight block">
                  110
                </span>
              </div>

              <div className="flex-1 px-2">
                <span className="text-[11px] text-indigo-600 block font-bold mb-1">
                  {lang === "ky" ? "Учурдагы балл" : "Текущий балл"}
                </span>
                <span className="text-3xl font-bold text-indigo-600 tracking-tight block">
                  {currentScore}
                </span>
              </div>

              <div className="flex-1 px-2">
                <span className="text-[11px] text-emerald-600 block font-bold mb-1">
                  {lang === "ky" ? "Максат" : "Цель"}
                </span>
                <span className="text-3xl font-bold text-emerald-600 tracking-tight block">
                  {targetScore}
                </span>
              </div>
            </div>

            {/* Gap summary pill */}
            <div className="flex items-center justify-between text-xs px-3.5 py-2.5 rounded-xl bg-emerald-50 text-emerald-800 font-medium mb-6">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>
                  {gap > 0
                    ? lang === "ky"
                      ? `Максатка жетүү үчүн дагы +${gap} балл керек`
                      : `До цели осталось набрать +${gap} баллов`
                    : lang === "ky"
                    ? "Максаттуу баллга жеттиңиз! Азаматсыз!"
                    : "Целевой балл достигнут! Отличная работа!"}
                </span>
              </div>
              <span className="font-bold text-[11px] text-emerald-700">
                {Math.min(100, Math.round((currentScore / targetScore) * 100))}%
              </span>
            </div>

            {/* Section Progress Breakdown */}
            <div className="space-y-3.5">
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                {lang === "ky" ? "Бөлүмдөр боюнча тактык жана дельта" : "Дельта роста по разделам"}
              </h4>

              {sectionData.map((sec) => {
                const delta = Math.max(0, sec.target - sec.current);
                const currentPct = Math.min(100, Math.round((sec.current / sec.max) * 100));

                return (
                  <div key={sec.nameKy} className="space-y-1.5">
                    <div className="flex justify-between text-xs font-semibold text-slate-700">
                      <span>{lang === "ky" ? sec.nameKy : sec.nameRu}</span>
                      <span className="text-slate-500 font-mono text-[11px]">
                        {sec.current} / {sec.max}{" "}
                        {delta > 0 && (
                          <span className="text-emerald-600 font-bold ml-1">+{delta}</span>
                        )}
                      </span>
                    </div>
                    <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-indigo-600 h-2 rounded-full transition-all duration-500"
                        style={{ width: `${currentPct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
