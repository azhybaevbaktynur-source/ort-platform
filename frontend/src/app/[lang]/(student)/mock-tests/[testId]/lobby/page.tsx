"use client";

import React, { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import {
  Clock,
  CheckCircle2,
  Play,
  ArrowLeft,
  ArrowRight,
  ShieldCheck,
  Award,
  Sparkles,
} from "lucide-react";

interface SectionInfo {
  id: string;
  name: { ky: string; ru: string };
  description: { ky: string; ru: string };
  questionCount: number;
  timeLimitMinutes: number;
  iconColor: string;
}

const ORT_SECTIONS: SectionInfo[] = [
  {
    id: "math_1",
    name: {
      ky: "1-Бөлүм: Математика I (Салыштыруу)",
      ru: "Раздел 1: Математика I (Сравнение величин)",
    },
    description: {
      ky: "А жана Б мамычаларындагы математикалык чоңдуктарды салыштыруу.",
      ru: "Количественное сравнение величин в колонках А и Б.",
    },
    questionCount: 30,
    timeLimitMinutes: 30,
    iconColor: "from-blue-600 to-indigo-600",
  },
  {
    id: "math_2",
    name: {
      ky: "2-Бөлүм: Математика II (Тест суроолору)",
      ru: "Раздел 2: Математика II (Задачи с выбором ответа)",
    },
    description: {
      ky: "Алгебра, геометрия, маселелер жана графиктерди анализдөө.",
      ru: "Алгебра, геометрия, текстовые задачи и анализ графиков.",
    },
    questionCount: 30,
    timeLimitMinutes: 30,
    iconColor: "from-rose-600 to-pink-600",
  },
  {
    id: "analogies",
    name: {
      ky: "3-Бөлүм: Аналогиялар жана сүйлөмдөрдү толуктоо",
      ru: "Раздел 3: Аналогии и дополнение предложений",
    },
    description: {
      ky: "Логикалык байланыштар, сөз байлыгы жана контекстти түшүнүү.",
      ru: "Логические связи между парами слов и контекстный выбор лексики.",
    },
    questionCount: 30,
    timeLimitMinutes: 30,
    iconColor: "from-emerald-600 to-teal-600",
  },
  {
    id: "reading",
    name: {
      ky: "4-Бөлүм: Окуу жана түшүнүү (Чоң тексттер)",
      ru: "Раздел 4: Чтение и понимание (Текстовые блоки)",
    },
    description: {
      ky: "Көлөмдүү илимий-популярдуу жана көркөм тексттер боюнча талдоо.",
      ru: "Глубокий анализ научно-популярных и литературных отрывков.",
    },
    questionCount: 30,
    timeLimitMinutes: 45,
    iconColor: "from-amber-600 to-orange-600",
  },
  {
    id: "grammar",
    name: {
      ky: "5-Бөлүм: Практикалык грамматика",
      ru: "Раздел 5: Практическая грамматика",
    },
    description: {
      ky: "Синтаксис, орфография, пунктуация жана сүйлөмдүн курулушу.",
      ru: "Синтаксис, орфография, пунктуация и стилистика предложений.",
    },
    questionCount: 30,
    timeLimitMinutes: 35,
    iconColor: "from-purple-600 to-indigo-600",
  },
];

function TestLobbyContent() {
  const params = useParams();
  const router = useRouter();
  const { lang, t } = useTranslation();
  const testId = (params?.testId as string) || "ort_main_standard";

  const [completedSections, setCompletedSections] = useState<string[]>([]);
  const [activeSectionId, setActiveSectionId] = useState<string>("math_1");

  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = sessionStorage.getItem(`ort_completed_sections_${testId}`);
      if (stored) {
        try {
          const parsed = JSON.parse(stored);
          if (Array.isArray(parsed)) {
            setCompletedSections(parsed);
            const firstUnfinished = ORT_SECTIONS.find((s) => !parsed.includes(s.id));
            if (firstUnfinished) {
              setActiveSectionId(firstUnfinished.id);
            }
          }
        } catch {
          // ignore
        }
      }
    }
  }, [testId]);

  const allCompleted = completedSections.length === ORT_SECTIONS.length;

  const handleStartSection = (sectionId: string) => {
    router.push(`/${lang}/mock-tests/${testId}?section=${sectionId}`);
  };

  const handleResetSession = () => {
    if (typeof window !== "undefined") {
      sessionStorage.removeItem(`ort_completed_sections_${testId}`);
      sessionStorage.removeItem(`ort_answers_${testId}`);
      sessionStorage.removeItem(`ort_result_${testId}`);
      setCompletedSections([]);
      setActiveSectionId("math_1");
    }
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto pb-12">
      {/* Back button & Breadcrumb */}
      <div className="flex items-center justify-between">
        <Link
          href={`/${lang}/mock-tests`}
          className="inline-flex items-center gap-2 text-xs font-bold text-slate-600 hover:text-slate-900 bg-white border border-slate-200 px-3.5 py-2 rounded-xl shadow-2xs transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{lang === "ky" ? "Бардык тесттерге кайтуу" : "Ко всем тестам"}</span>
        </Link>

        {completedSections.length > 0 && (
          <button
            onClick={handleResetSession}
            className="text-xs font-semibold text-rose-600 hover:text-rose-700 hover:underline"
          >
            {lang === "ky" ? "Тестти башынан баштоо" : "Сбросить прогресс"}
          </button>
        )}
      </div>

      {/* Main Lobby Hero Card */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 shadow-sm space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-6">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-50 text-brand-700 text-xs font-bold border border-brand-200">
              <Sparkles className="w-3.5 h-3.5 text-brand-600" />
              <span>{lang === "ky" ? "Расмий ОРТ Форматы" : "Официальный Формат ОРТ"}</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              {lang === "ky" ? "ОРТ Негизги Тест (Толук Формат)" : "ОРТ Основной Тест (Полный Формат)"}
            </h1>
            <p className="text-sm text-slate-600 max-w-2xl leading-relaxed">
              {lang === "ky"
                ? "Экзамен 5 өзүнчө бөлүмдөн турат. Ар бир бөлүм өз убактысына ээ жана бүткөндөн кийин автоматтык түрдө жабылат. Бөлүмдөрдү кезектешип тапшырыңыз."
                : "Тест разделен на 5 строгих изолированных секций. Каждая секция имеет собственный независимый таймер. Переход осуществляется последовательно."}
            </p>
          </div>

          {/* Test Stats Header Badge */}
          <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 sm:min-w-[200px] flex sm:flex-col justify-around gap-2 text-center">
            <div>
              <span className="text-[11px] text-slate-500 font-semibold block uppercase">
                {lang === "ky" ? "Жалпы убакыт" : "Общее время"}
              </span>
              <span className="text-lg font-extrabold text-slate-900 flex items-center justify-center gap-1">
                <Clock className="w-4 h-4 text-brand-600" />
                <span>170 {lang === "ky" ? "мүнөт" : "минут"}</span>
              </span>
            </div>
            <div className="border-t border-slate-200 pt-2">
              <span className="text-[11px] text-slate-500 font-semibold block uppercase">
                {lang === "ky" ? "Суроолор" : "Вопросы"}
              </span>
              <span className="text-lg font-extrabold text-slate-900">
                150 {lang === "ky" ? "суроо" : "вопросов"}
              </span>
            </div>
          </div>
        </div>

        {/* Progress Tracker Bar */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold">
            <span className="text-slate-700">
              {lang === "ky" ? "Тесттин аткарылышы:" : "Прогресс прохождения теста:"}
            </span>
            <span className="text-brand-600">
              {completedSections.length} / {ORT_SECTIONS.length} {lang === "ky" ? "бөлүм аякталды" : "секций завершено"}
            </span>
          </div>
          <div className="w-full h-3 rounded-full bg-slate-100 overflow-hidden">
            <div
              className="h-full bg-brand-600 transition-all duration-500 rounded-full"
              style={{ width: `${(completedSections.length / ORT_SECTIONS.length) * 100}%` }}
            />
          </div>
        </div>
      </div>

      {/* Sections List */}
      <div className="space-y-4">
        <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-brand-600" />
          <span>{lang === "ky" ? "Экзамендик бөлүмдөрдүн тизмеси:" : "Секции экзамена:"}</span>
        </h2>

        <div className="grid grid-cols-1 gap-4">
          {ORT_SECTIONS.map((sec, idx) => {
            const isCompleted = completedSections.includes(sec.id);
            const isCurrent = !isCompleted && sec.id === activeSectionId;

            return (
              <div
                key={sec.id}
                className={`bg-white rounded-3xl border-2 p-5 sm:p-6 transition-all shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-5 ${
                  isCompleted
                    ? "border-emerald-200 bg-emerald-50/20"
                    : isCurrent
                    ? "border-brand-500 ring-4 ring-brand-100/60"
                    : "border-slate-200 opacity-80"
                }`}
              >
                <div className="flex items-start gap-4">
                  <div
                    className={`w-12 h-12 rounded-2xl bg-gradient-to-br ${sec.iconColor} text-white flex items-center justify-center font-extrabold text-base flex-shrink-0 shadow-xs`}
                  >
                    {idx + 1}
                  </div>

                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-bold text-base text-slate-900">
                        {lang === "ky" ? sec.name.ky : sec.name.ru}
                      </h3>
                      {isCompleted ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>{lang === "ky" ? "Аякталды" : "Завершено"}</span>
                        </span>
                      ) : isCurrent ? (
                        <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-brand-100 text-brand-800 animate-pulse">
                          {lang === "ky" ? "Кезектеги бөлүм" : "Следующий"}
                        </span>
                      ) : (
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                          {lang === "ky" ? "Баштала элек" : "Ожидает"}
                        </span>
                      )}
                    </div>

                    <p className="text-xs text-slate-600 leading-relaxed max-w-xl">
                      {lang === "ky" ? sec.description.ky : sec.description.ru}
                    </p>

                    <div className="flex items-center gap-4 text-xs text-slate-500 pt-1 font-medium">
                      <span className="flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5 text-slate-400" />
                        <span>{sec.questionCount} {lang === "ky" ? "суроо" : "вопросов"}</span>
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5 text-slate-400" />
                        <span>{sec.timeLimitMinutes} {lang === "ky" ? "мүнөт" : "минут"}</span>
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex sm:flex-col items-center justify-end sm:items-end gap-2 flex-shrink-0">
                  {isCompleted ? (
                    <button
                      onClick={() => handleStartSection(sec.id)}
                      className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl border border-emerald-300 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 font-semibold text-xs transition-colors"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      <span>{lang === "ky" ? "Кайра кароо" : "Просмотр"}</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => handleStartSection(sec.id)}
                      className={`inline-flex items-center justify-center gap-2 px-6 py-3 rounded-2xl font-bold text-xs shadow-xs transition-all ${
                        isCurrent
                          ? "bg-brand-600 hover:bg-brand-700 text-white scale-105"
                          : "bg-slate-900 hover:bg-slate-800 text-white"
                      }`}
                    >
                      <Play className="w-3.5 h-3.5 fill-current" />
                      <span>{lang === "ky" ? "Бөлүмдү баштоо" : "Начать секцию"}</span>
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Completion Action Card */}
      {allCompleted && (
        <div className="bg-gradient-to-r from-emerald-600 to-teal-700 text-white p-6 sm:p-8 rounded-3xl shadow-md flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="space-y-1 text-center sm:text-left">
            <h3 className="text-xl font-extrabold flex items-center gap-2 justify-center sm:justify-start">
              <Award className="w-6 h-6 text-amber-300" />
              <span>{lang === "ky" ? "Бардык бөлүмдөр ийгиликтүү аяктады!" : "Все разделы успешно завершены!"}</span>
            </h3>
            <p className="text-xs text-emerald-100">
              {lang === "ky"
                ? "Сиз 150 суроону толук бүтүрдүңүз. Жыйынтык баракчасына өтүп, ОРТ 60-245 шкаласындагы балыңызды көрүңүз."
                : "Вы прошли все 150 вопросов. Перейдите к ведомости результатов для расчета шкалы ОРТ 60-245."}
            </p>
          </div>

          <Link
            href={`/${lang}/mock-tests/${testId}/result`}
            className="inline-flex items-center gap-2 px-6 py-3.5 rounded-2xl bg-white text-emerald-900 hover:bg-emerald-50 font-extrabold text-sm shadow-md transition-all flex-shrink-0"
          >
            <span>{lang === "ky" ? "Жыйынтыкты көрүү" : "Посмотреть результат"}</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      )}
    </div>
  );
}

export default function TestLobbyPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-slate-500">Loading lobby...</div>}>
      <TestLobbyContent />
    </Suspense>
  );
}

