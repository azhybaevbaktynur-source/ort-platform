"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { apiClient } from "@/lib/api";
import { CheckCircle2, Circle, Flame, Calendar, Clock, Loader2 } from "lucide-react";

interface DailyTask {
  id: string;
  title: { ky: string; ru: string };
  section: string;
  questionCount: number;
  isCompleted: boolean;
}

interface DailyPlannerResponse {
  date: string;
  streakCount: number;
  tasks: DailyTask[];
  dailyGoalCompleted: boolean;
  estimatedStudyMinutes: number;
}

export const DailyPlannerWidget: React.FC = () => {
  const { lang, t } = useTranslation();

  const [tasks, setTasks] = useState<DailyTask[]>([
    {
      id: "task_1",
      title: {
        ky: "Математика I: 15 сызыктуу теңдеме суроолорун чыгаргыла",
        ru: "Математика I: Решите 15 задач на линейные уравнения",
      },
      section: "math_1",
      questionCount: 15,
      isCompleted: false,
    },
    {
      id: "task_2",
      title: {
        ky: "Аналогиялар: 20 сөз айкашы боюнча машыгуу",
        ru: "Аналогии: 20 заданий на сопоставление пар слов",
      },
      section: "analogies",
      questionCount: 20,
      isCompleted: false,
    },
    {
      id: "task_3",
      title: {
        ky: "Окуу жана түшүнүү: 1 текстти талдап, суроолоруна жооп бергиле",
        ru: "Чтение и понимание: Проанализируйте 1 текст и ответьте на вопросы",
      },
      section: "reading",
      questionCount: 10,
      isCompleted: false,
    },
  ]);
  const [streakCount, setStreakCount] = useState(7);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    async function fetchPlanner() {
      try {
        const data = await apiClient<DailyPlannerResponse>("/planner/daily");
        if (!isMounted) return;
        if (data.tasks && data.tasks.length > 0) {
          setTasks(data.tasks);
        }
        if (typeof data.streakCount === "number") {
          setStreakCount(data.streakCount);
        }
      } catch {
        // Fallback default tasks if backend is loading or offline
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }
    fetchPlanner();
    return () => {
      isMounted = false;
    };
  }, []);

  const toggleTask = async (taskId: string) => {
    const targetTask = tasks.find((t) => t.id === taskId);
    if (!targetTask) return;

    const nextCompleted = !targetTask.isCompleted;

    // Optimistic update
    setTasks((prev) =>
      prev.map((item) =>
        item.id === taskId ? { ...item, isCompleted: nextCompleted } : item
      )
    );

    try {
      await apiClient("/planner/toggle-task", {
        method: "POST",
        body: JSON.stringify({
          taskId,
          isCompleted: nextCompleted,
        }),
      });
    } catch {
      // Revert if error
      setTasks((prev) =>
        prev.map((item) =>
          item.id === taskId ? { ...item, isCompleted: !nextCompleted } : item
        )
      );
    }
  };

  const completedCount = tasks.filter((t) => t.isCompleted).length;
  const progressPercent =
    tasks.length > 0 ? Math.round((completedCount / tasks.length) * 100) : 0;

  return (
    <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs flex flex-col justify-between">
      <div>
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="flex items-center gap-2">
              <Calendar className="w-5 h-5 text-indigo-600" />
              <h3 className="font-bold text-slate-900 text-lg">
                {lang === "ky" ? "Бүгүнкү Окуу Планы" : "План Обучения на Сегодня"}
              </h3>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              {lang === "ky"
                ? "Алтын сертификатка карай күндүк кадамдарыңыз"
                : "Ваши ежедневные шаги к Золотому сертификату"}
            </p>
          </div>

          {/* Streak Pill */}
          <div className="flex items-center bg-amber-50 border border-amber-200 text-amber-800 px-3 py-1.5 rounded-xl font-bold text-xs shadow-xs">
            <Flame className="w-4 h-4 fill-amber-500 text-amber-500 mr-1.5" />
            <span>
              {streakCount} {lang === "ky" ? "күн катар!" : "дней подряд!"}
            </span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="mb-5">
          <div className="flex justify-between text-xs font-semibold mb-1.5 text-slate-700">
            <span>{lang === "ky" ? "Бүгүнкү максат" : "Прогресс дня"}</span>
            <span>
              {completedCount} / {tasks.length} ({progressPercent}%)
            </span>
          </div>
          <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
            <div
              className="bg-indigo-600 h-2.5 rounded-full transition-all duration-500"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {/* Task Checklist */}
        {isLoading ? (
          <div className="flex items-center justify-center p-8 text-slate-400">
            <Loader2 className="w-6 h-6 animate-spin text-indigo-600" />
          </div>
        ) : (
          <div className="space-y-2.5">
            {tasks.map((task) => {
              const title =
                lang === "ky"
                  ? task.title?.ky || task.title?.ru
                  : task.title?.ru || task.title?.ky;
              return (
                <div
                  key={task.id}
                  onClick={() => toggleTask(task.id)}
                  className={`flex items-start p-3 rounded-2xl border transition-all cursor-pointer select-none ${
                    task.isCompleted
                      ? "bg-emerald-50/50 border-emerald-200 text-slate-500"
                      : "bg-slate-50 hover:bg-slate-100/80 border-slate-200/80 text-slate-800"
                  }`}
                >
                  <button type="button" className="mt-0.5 mr-3 shrink-0">
                    {task.isCompleted ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-600 fill-emerald-100" />
                    ) : (
                      <Circle className="w-5 h-5 text-slate-400 hover:text-indigo-600" />
                    )}
                  </button>

                  <div className="flex-1 text-xs">
                    <span
                      className={`block font-medium ${
                        task.isCompleted
                          ? "line-through text-slate-400"
                          : "text-slate-800"
                      }`}
                    >
                      {title}
                    </span>
                    <span className="inline-flex items-center text-[11px] text-slate-400 mt-1 gap-1">
                      <Clock className="w-3 h-3" />
                      {task.questionCount} {lang === "ky" ? "суроо" : "вопросов"} (~15 мин)
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
