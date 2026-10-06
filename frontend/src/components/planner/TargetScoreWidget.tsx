"use client";

import React, { useEffect, useState, useRef } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { apiClient } from "@/lib/api";
import { Award, TrendingUp, Loader2, ChevronDown, Check } from "lucide-react";

const TARGET_OPTIONS = [
  { value: 110, descKy: "Босого балл", descRu: "Пороговый балл" },
  { value: 140, descKy: "ЖОЖдорго кабыл алуу", descRu: "Поступление в ВУЗ" },
  { value: 160, descKy: "Орточо балл", descRu: "Средний балл" },
  { value: 175, descKy: "Бюджет / Гранттык орундар", descRu: "Бюджет / Грант" },
  { value: 190, descKy: "Престиждүү адистиктер", descRu: "Престижные специальности" },
  { value: 200, descKy: "Топ-Университеттер", descRu: "Топ-Университеты" },
  { value: 219, descKy: "Алтын сертификат (босого)", descRu: "Золотой сертификат" },
  { value: 230, descKy: "Мыкты натыйжа", descRu: "Высокий результат" },
  { value: 245, descKy: "Максималдуу балл", descRu: "Максимум" },
];

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
  exams_taken?: number;
  starting_score?: number;
  totalQuestionsPracticed: number;
  overallAccuracy: number;
  sectionsMastery: Record<string, SectionMastery>;
  recentScores: Array<{ date: string; scaled: number; raw: number }>;
}

interface UserProfileResponse {
  id: string;
  displayName: string;
  currentEstimatedScore?: number;
  exams_taken?: number;
  starting_score?: number;
  target_score?: number;
  targetScore?: {
    overall: number;
    math: number;
    reading: number;
    grammar: number;
    analogies: number;
  };
}

export const TargetScoreWidget: React.FC = () => {
  const { lang, t } = useTranslation();
  const { updateTargetScore, userProfile } = useAuth();

  const [isLoading, setIsLoading] = useState(true);
  const [currentScore, setCurrentScore] = useState(0);
  const [targetScore, setTargetScore] = useState(userProfile?.target_score || 200);
  const [startingScore, setStartingScore] = useState(0);
  const [examsTaken, setExamsTaken] = useState(0);
  const [gap, setGap] = useState(0);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsDropdownOpen(false);
      }
    }
    if (isDropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isDropdownOpen]);
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

        let cur = 0;
        let tgt = userProfile?.target_score || 200;
        let taken = 0;
        let start = 0;
        let mastery: Record<string, SectionMastery> = {};
        let tgtBreakdown = { math: 50, reading: 25, grammar: 25, analogies: 25 };

        if (profile.status === "fulfilled" && profile.value) {
          tgt = profile.value.target_score || profile.value.targetScore?.overall || tgt;
          taken = profile.value.exams_taken ?? taken;
          start = profile.value.starting_score ?? start;
          cur = profile.value.currentEstimatedScore ?? cur;
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
          const a = analytics.value;
          taken = a.totalTestsCompleted ?? a.exams_taken ?? taken;
          tgt = a.targetScore || tgt;
          mastery = a.sectionsMastery || {};
          if (taken > 0) {
            cur = a.currentEstimatedScore || cur;
            start = a.starting_score || (a.recentScores && a.recentScores[0]?.scaled) || start || cur;
          } else {
            cur = 0;
            start = 0;
          }
        }

        setExamsTaken(taken);
        setCurrentScore(cur);
        setStartingScore(start);
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
  }, [userProfile?.target_score]);

  const handleTargetScoreChange = async (newScore: number) => {
    if (isNaN(newScore)) return;
    const clamped = Math.max(60, Math.min(245, newScore));
    // 1. Optimistic UI update
    setTargetScore(clamped);
    setGap(Math.max(0, clamped - currentScore));

    // 2. Auth context update & localStorage sync & DB persist via API
    try {
      await updateTargetScore(clamped);
    } catch (e) {
      console.warn("Failed to persist target score:", e);
    }
  };

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
                <span className="text-2xl md:text-3xl font-bold text-slate-700 tracking-tight block">
                  {examsTaken > 0 ? (startingScore || 110) : "—"}
                </span>
              </div>

              <div className="flex-1 px-2">
                <span className="text-[11px] text-indigo-600 block font-bold mb-1">
                  {lang === "ky" ? "Учурдагы балл" : "Текущий балл"}
                </span>
                {examsTaken > 0 ? (
                  <span className="text-2xl md:text-3xl font-bold text-indigo-600 tracking-tight block">
                    {currentScore}
                  </span>
                ) : (
                  <span className="text-[11px] font-semibold text-slate-400 block py-1.5 leading-tight">
                    {lang === "ky" ? "Сыноо тапшырыла элек" : "Тест еще не сдан"}
                  </span>
                )}
              </div>

              <div className="flex-1 px-2 relative" ref={dropdownRef}>
                <span className="text-[11px] text-emerald-600 block font-bold mb-1">
                  {lang === "ky" ? "Максат (балл)" : "Цель (балл)"}
                </span>
                <div className="flex flex-col items-center gap-1.5">
                  <div className="relative inline-block">
                    <button
                      type="button"
                      onClick={() => setIsDropdownOpen((prev) => !prev)}
                      className="px-4 py-2 bg-emerald-50 text-emerald-700 rounded-xl font-bold hover:bg-emerald-100 transition-all cursor-pointer whitespace-nowrap inline-flex items-center justify-center gap-1.5 border border-emerald-200/60 shadow-xs"
                      aria-expanded={isDropdownOpen}
                      aria-haspopup="listbox"
                    >
                      <span>
                        {targetScore} {lang === "ky" ? "балл" : "баллов"}
                      </span>
                      <ChevronDown
                        className={`w-4 h-4 text-emerald-600 transition-transform duration-200 ${
                          isDropdownOpen ? "rotate-180" : ""
                        }`}
                      />
                    </button>

                    {/* Floating Menu Layout */}
                    {isDropdownOpen && (
                      <div
                        role="listbox"
                        className="absolute right-0 top-full mt-2 w-64 sm:w-72 max-w-[90vw] bg-white shadow-xl rounded-2xl border border-gray-100 p-1 z-50 overflow-hidden text-left animate-in fade-in zoom-in-95 duration-150"
                      >
                        <ul className="max-h-64 overflow-y-auto space-y-0.5 list-none p-0 m-0">
                          {TARGET_OPTIONS.map((opt) => {
                            const isSelected = targetScore === opt.value;
                            return (
                              <li
                                key={opt.value}
                                role="option"
                                aria-selected={isSelected}
                                onClick={() => {
                                  handleTargetScoreChange(opt.value);
                                  setIsDropdownOpen(false);
                                }}
                                className={`px-4 py-3 text-sm rounded-lg cursor-pointer transition-colors flex items-center justify-between gap-2 ${
                                  isSelected
                                    ? "bg-emerald-50 text-emerald-700 font-bold"
                                    : "text-gray-700 hover:bg-gray-50"
                                }`}
                              >
                                <div className="flex flex-col">
                                  <span className="font-bold flex items-center gap-1.5">
                                    {opt.value} {lang === "ky" ? "балл" : "баллов"}
                                    {opt.value >= 219 && (
                                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800">
                                        {lang === "ky" ? "Алтын" : "Золото"}
                                      </span>
                                    )}
                                  </span>
                                  <span className="text-xs text-gray-500 font-normal">
                                    {lang === "ky" ? opt.descKy : opt.descRu}
                                  </span>
                                </div>
                                {isSelected && (
                                  <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    )}
                  </div>

                  <input
                    type="range"
                    min={60}
                    max={245}
                    step={5}
                    value={targetScore}
                    onChange={(e) => handleTargetScoreChange(Number(e.target.value))}
                    className="w-full max-w-[140px] accent-emerald-600 cursor-pointer"
                    title={lang === "ky" ? "Максаттуу баллды тууралоо" : "Настроить целевой балл ползунком"}
                  />
                </div>
              </div>
            </div>

            {/* Gap summary pill */}
            {examsTaken === 0 ? (
              <div className="flex items-center justify-between text-xs px-3.5 py-2.5 rounded-xl bg-slate-100 text-slate-700 font-medium mb-6">
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-slate-500 shrink-0" />
                  <span>
                    {lang === "ky"
                      ? "Биринчи сынамык тестти тапшырып, учурдагы деңгээлиңизди аныктаңыз"
                      : "Сдайте первый тест, чтобы определить ваш начальный уровень"}
                  </span>
                </div>
                <span className="font-bold text-[11px] text-slate-500">0%</span>
              </div>
            ) : (
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
            )}

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
