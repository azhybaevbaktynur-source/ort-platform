"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import { Award, CheckCircle2, XCircle, BarChart3, RotateCcw, ArrowRight } from "lucide-react";

export default function MockTestResultPage() {
  const params = useParams();
  const { lang, t } = useTranslation();
  const testId = (params?.testId as string) || "ort_main_standard";

  const [resultData, setResultData] = useState<any>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = sessionStorage.getItem(`ort_result_${testId}`);
      if (stored) {
        try {
          setResultData(JSON.parse(stored));
        } catch {
          // ignore parse error
        }
      }
    }
  }, [testId]);

  // Demo calibrated results
  const scaledScore = 194;
  const percentile = 88.5;
  const isGolden = scaledScore >= 219;

  const sectionBreakdown = [
    { name: t("sections.math_1"), raw: "1 / 1", scaled: 45, accuracy: 100 },
    { name: t("sections.analogies"), raw: "1 / 1", scaled: 42, accuracy: 100 },
    { name: t("sections.reading"), raw: "1 / 1", scaled: 40, accuracy: 100 },
    { name: t("sections.grammar"), raw: "0 / 1", scaled: 30, accuracy: 0 },
    { name: t("sections.math_2"), raw: "1 / 1", scaled: 47, accuracy: 100 },
  ];

  const reviewedQuestions = [
    {
      id: "mq_1",
      stem: {
        ky: "Эгер $y = 2x + 4$ жана $x = 3$ болсо, $y$ тин мааниси канчага барабар?",
        ru: "Если $y = 2x + 4$ и $x = 3$, найдите значение $y$:",
      },
      userChoice: "B",
      correctOption: "B",
      isCorrect: true,
      explanation: {
        ky: "Теңдемеге $x = 3$ коёбуз: $y = 2(3) + 4 = 10$. Туура жооп Б.",
        ru: "Подставим $x = 3$: $y = 2(3) + 4 = 10$. Верный ответ Б.",
      },
    },
    {
      id: "mq_2",
      stem: {
        ky: "Баштапкы жупка маанилик жактан эң жакын жупту тандагыла:\n\n**КҮН : ЖАРЫК**",
        ru: "Выберите пару, наиболее близкую по значению к исходной:\n\n**СОЛНЦЕ : СВЕТ**",
      },
      userChoice: "C",
      correctOption: "C",
      isCorrect: true,
      explanation: {
        ky: "Күн жарык бергендей эле, от жылуулук берет. Туура жооп: От : Жылуулук.",
        ru: "Как солнце дает свет, так огонь дает тепло. Верный ответ: Огонь : Тепло.",
      },
    },
    {
      id: "mq_4",
      stem: {
        ky: "Төмөнкү сүйлөмдө кайсы сөз өтмө мааниде колдонулган?\n\n*«Айгүлдүн алтын колу ар кандай уз чеберчиликке жетет.»*",
        ru: "В каком предложении слово употреблено в переносном значении?\n\n*«У Айгуль золотые руки, она способна на любое мастерство.»*",
      },
      userChoice: "C",
      correctOption: "B",
      isCorrect: false,
      explanation: {
        ky: "«Алтын кол» — металл эмес, чеберчиликти билдирген өтмө маанидеги (метафора) сөз. Туура жооп: Б.",
        ru: "«Золотые руки» — метафора, означающая искусность мастера. Правильный ответ: Б.",
      },
    },
  ];

  return (
    <div className="space-y-8">
      {/* Top Banner Score Summary */}
      <div className="bg-white rounded-3xl border border-slate-200 p-8 shadow-sm text-center relative overflow-hidden">
        <div className="max-w-xl mx-auto space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-bold">
            <CheckCircle2 className="w-4 h-4" />
            <span>{t("exam.scoreReport")}</span>
          </div>

          <h2 className="text-3xl font-extrabold text-slate-900">
            {lang === "ky" ? "Тестирлөө ийгиликтүү аяктады!" : "Тестирование успешно завершено!"}
          </h2>

          <div className="py-6 flex items-center justify-center gap-8 border-y border-slate-100 my-4">
            <div>
              <span className="text-xs text-slate-400 font-semibold block uppercase">
                {t("exam.scaledScore")}
              </span>
              <span className="text-5xl font-black text-brand-600 tracking-tight">
                {scaledScore}
              </span>
              <span className="text-xs text-slate-400 block mt-1">шкала 60-245</span>
            </div>

            <div className="w-px h-16 bg-slate-200" />

            <div>
              <span className="text-xs text-slate-400 font-semibold block uppercase">
                {t("exam.percentile")}
              </span>
              <span className="text-5xl font-black text-emerald-600 tracking-tight">
                {percentile}%
              </span>
              <span className="text-xs text-slate-400 block mt-1">Кыргызстан боюнча</span>
            </div>
          </div>

          {/* Golden Certificate status badge */}
          <div
            className={`p-4 rounded-2xl border text-xs font-semibold flex items-center justify-center gap-2 ${
              isGolden
                ? "bg-amber-50 border-amber-300 text-amber-900"
                : "bg-slate-50 border-slate-200 text-slate-700"
            }`}
          >
            <Award className="w-5 h-5 text-amber-500 flex-shrink-0" />
            <span>
              {isGolden
                ? lang === "ky"
                  ? "Куттуктайбыз! Сиз Алтын сертификаттын босогосунан (219+) аштыңыз!"
                  : "Поздравляем! Вы превысили порог Золотого сертификата (219+)!"
                : lang === "ky"
                ? `Алтын сертификатка (219+) чейин дагы +${219 - scaledScore} балл калды. Каталар менен иштеп, машыгууну улантыңыз!`
                : `До Золотого сертификата (219+) осталось +${219 - scaledScore} баллов. Продолжайте тренировки!`}
            </span>
          </div>

          {/* CTAs */}
          <div className="pt-2 flex justify-center gap-3">
            <Link
              href={`/${lang}/mistakes`}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-slate-900 text-white font-semibold text-xs hover:bg-slate-800 transition-colors"
            >
              <span>{lang === "ky" ? "Каталар менен иштөө" : "Разбор ошибок"}</span>
              <ArrowRight className="w-4 h-4" />
            </Link>

            <Link
              href={`/${lang}/mock-tests`}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-700 font-semibold text-xs hover:bg-slate-50 transition-colors"
            >
              <RotateCcw className="w-4 h-4" />
              <span>{lang === "ky" ? "Башка тест тапшыруу" : "Пройти другой тест"}</span>
            </Link>
          </div>
        </div>
      </div>

      {/* Section Breakdown Grid */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-6">
          <BarChart3 className="w-5 h-5 text-brand-600" />
          <h3 className="font-bold text-slate-900 text-lg">
            {t("exam.sectionBreakdown")}
          </h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          {sectionBreakdown.map((sec) => (
            <div key={sec.name} className="p-4 rounded-xl border border-slate-100 bg-slate-50/60 space-y-2">
              <span className="text-xs font-bold text-slate-700 block truncate">{sec.name}</span>
              <div className="flex justify-between items-baseline">
                <span className="text-2xl font-extrabold text-slate-900">{sec.scaled}</span>
                <span className="text-xs font-bold text-emerald-600">{sec.accuracy}%</span>
              </div>
              <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                <div className="bg-brand-500 h-1.5 rounded-full" style={{ width: `${sec.accuracy}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Detailed Question Review */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-6">
        <h3 className="font-bold text-slate-900 text-lg">
          {lang === "ky" ? "Суроолорду деталдуу талдоо" : "Детальный разбор вопросов"}
        </h3>

        <div className="space-y-4">
          {reviewedQuestions.map((q, idx) => (
            <div
              key={q.id}
              className={`p-5 rounded-2xl border space-y-3 ${
                q.isCorrect ? "border-emerald-200 bg-emerald-50/30" : "border-rose-200 bg-rose-50/30"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-500">
                  {lang === "ky" ? `Суроо №${idx + 1}` : `Вопрос №${idx + 1}`}
                </span>
                <span
                  className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                    q.isCorrect ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"
                  }`}
                >
                  {q.isCorrect ? "Туура / Верно" : "Ката / Ошибка"}
                </span>
              </div>

              <MathRenderer content={lang === "ky" ? q.stem.ky : q.stem.ru} className="text-sm font-medium" />

              <div className="flex gap-4 text-xs">
                <div>
                  <span className="text-slate-500">{t("exam.yourAnswer")}: </span>
                  <span className={`font-bold ${q.isCorrect ? "text-emerald-700" : "text-rose-700"}`}>
                    {q.userChoice}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">{t("exam.correctAnswer")}: </span>
                  <span className="font-bold text-emerald-700">{q.correctOption}</span>
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-white border border-slate-200/80 text-xs">
                <span className="font-bold text-slate-700 block mb-1">{t("exam.explanation")}:</span>
                <MathRenderer
                  content={lang === "ky" ? q.explanation.ky : q.explanation.ru}
                  className="text-slate-600 leading-relaxed"
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

