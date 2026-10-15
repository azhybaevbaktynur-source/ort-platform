"use client";

import React, { useState, useEffect } from "react";
import { useTranslation } from "@/lib/i18n/context";
import {
  BookOpenCheck,
  Plus,
  Lock,
  Unlock,
  Calendar,
  KeyRound,
  Users,
  Edit2,
  Trash2,
  UploadCloud,
  CheckCircle2,
  AlertCircle,
  Clock,
  HelpCircle,
  X,
  RefreshCw,
  Search,
} from "lucide-react";
import Link from "next/link";
import { getAuthHeader } from "@/lib/api";
import { toast } from "@/components/ui/Toast";

interface SectionConfig {
  section: string;
  questionCount: number;
  timeLimitMinutes: number;
}

interface ExamSet {
  id: string;
  title: string;
  description?: string;
  language: string;
  type: string;
  exam_type?: "full_main" | "subject" | "practice_bank";
  status: "draft" | "published";
  available_from?: string | null;
  available_until?: string | null;
  access_code?: string | null;
  max_attempts: number;
  sections: SectionConfig[];
  totalQuestions: number;
  totalTimeMinutes: number;
  time_limit_minutes?: number | null;
  question_count?: number;
  questionIds: string[];
  completionsCount: number;
  createdAt?: string;
  updatedAt?: string;
}

export default function ExamManagementPage() {
  const { lang, t } = useTranslation();
  const [exams, setExams] = useState<ExamSet[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterLang, setFilterLang] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [filterType, setFilterType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingExam, setEditingExam] = useState<ExamSet | null>(null);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Form Fields
  const [formTitle, setFormTitle] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formLanguage, setFormLanguage] = useState<"ky" | "ru">("ky");
  const [formExamType, setFormExamType] = useState<"full_main" | "subject" | "practice_bank">("full_main");
  const [formStatus, setFormStatus] = useState<"draft" | "published">("published");
  const [formAccessCode, setFormAccessCode] = useState("");
  const [formMaxAttempts, setFormMaxAttempts] = useState(1);
  const [formTimeLimitMinutes, setFormTimeLimitMinutes] = useState<number | "">("");
  const [formAvailableFrom, setFormAvailableFrom] = useState("");
  const [formAvailableUntil, setFormAvailableUntil] = useState("");

  const fetchExams = async () => {
    try {
      setLoading(true);
      const authHeader = await getAuthHeader();
      const res = await fetch("/api/v1/mock-tests/exam-sets", {
        headers: authHeader,
      });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          const uniqueExams: ExamSet[] = Array.from(
            new Map(data.map((item: any) => [item.id, item])).values()
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
  }, []);

  const openCreateModal = () => {
    setEditingExam(null);
    setFormTitle("");
    setFormDescription("");
    setFormLanguage("ky");
    setFormExamType("full_main");
    setFormStatus("published");
    setFormAccessCode("");
    setFormMaxAttempts(1);
    setFormTimeLimitMinutes("");
    setFormAvailableFrom("");
    setFormAvailableUntil("");
    setErrorMsg(null);
    setIsModalOpen(true);
  };

  const openEditModal = (exam: ExamSet) => {
    setEditingExam(exam);
    setFormTitle(exam.title);
    setFormDescription(exam.description || "");
    setFormLanguage((exam.language as "ky" | "ru") || "ky");
    setFormExamType((exam.exam_type as any) || "full_main");
    setFormStatus(exam.status || "published");
    setFormAccessCode(exam.access_code || "");
    setFormMaxAttempts(exam.max_attempts || 1);
    setFormTimeLimitMinutes(exam.time_limit_minutes ?? "");
    setFormAvailableFrom(exam.available_from ? exam.available_from.slice(0, 16) : "");
    setFormAvailableUntil(exam.available_until ? exam.available_until.slice(0, 16) : "");
    setErrorMsg(null);
    setIsModalOpen(true);
  };

  const handleToggleStatus = async (exam: ExamSet) => {
    const nextStatus = exam.status === "published" ? "draft" : "published";
    try {
      const authHeader = await getAuthHeader();
      const res = await fetch(`/api/v1/mock-tests/exam-sets/${exam.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeader,
        },
        body: JSON.stringify({ status: nextStatus }),
      });
      if (res.ok) {
        setExams((prev) =>
          prev.map((e) => (e.id === exam.id ? { ...e, status: nextStatus } : e))
        );
      }
    } catch (err) {
      console.error("Failed to toggle status:", err);
    }
  };

  const handleDelete = async (examId: string) => {
    if (
      !confirm(
        lang === "ky"
          ? "Бул экзамен топтомун өчүрүүнү каалайсызбы?"
          : "Вы уверены, что хотите удалить этот экзамен?"
      )
    ) {
      return;
    }

    try {
      const authHeader = await getAuthHeader();
      const res = await fetch(`/api/v1/mock-tests/exam-sets/${examId}`, {
        method: "DELETE",
        headers: authHeader,
      });
      if (res.ok) {
        setExams((prev) => prev.filter((e) => e.id !== examId));
        toast.success(lang === "ky" ? "Экзамен топтому өчүрүлдү" : "Экзаменационный сет успешно удален");
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || (lang === "ky" ? "Экзаменди өчүрүү катасы" : "Ошибка при удалении экзамена"));
      }
    } catch (err: any) {
      console.error("Failed to delete exam:", err);
      toast.error(err.message || (lang === "ky" ? "Ката кетти" : "Произошла ошибка"));
    }
  };

  const handleSaveExam = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formTitle.trim()) {
      setErrorMsg(lang === "ky" ? "Аталышын жазыңыз" : "Укажите название");
      return;
    }

    setSaving(true);
    setErrorMsg(null);

    const payload = {
      title: formTitle.trim(),
      description: formDescription.trim() || undefined,
      language: formLanguage,
      exam_type: formExamType,
      status: formStatus,
      access_code: formAccessCode.trim() ? formAccessCode.trim() : null,
      max_attempts: Number(formMaxAttempts) || 1,
      time_limit_minutes: formTimeLimitMinutes ? Number(formTimeLimitMinutes) : null,
      available_from: formAvailableFrom ? new Date(formAvailableFrom).toISOString() : null,
      available_until: formAvailableUntil ? new Date(formAvailableUntil).toISOString() : null,
      sections: editingExam?.sections || [
        { section: "math_1", questionCount: 30, timeLimitMinutes: 30 },
        { section: "math_2", questionCount: 30, timeLimitMinutes: 30 },
        { section: "reading", questionCount: 30, timeLimitMinutes: 45 },
        { section: "analogies", questionCount: 30, timeLimitMinutes: 30 },
        { section: "grammar", questionCount: 30, timeLimitMinutes: 35 },
      ],
    };

    try {
      const url = editingExam
        ? `/api/v1/mock-tests/exam-sets/${editingExam.id}`
        : "/api/v1/mock-tests/exam-sets";
      const method = editingExam ? "PUT" : "POST";

      const authHeader = await getAuthHeader();
      const res = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          ...authHeader,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Error saving exam set");
      }

      setIsModalOpen(false);
      await fetchExams();
      toast.success(
        editingExam
          ? (lang === "ky" ? "Экзамен топтому жаңыланды" : "Экзаменационный сет обновлен")
          : (lang === "ky" ? "Жаңы экзамен түзүлдү" : "Экзаменационный сет успешно создан")
      );
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to save");
      toast.error(err.message || (lang === "ky" ? "Сактоо катасы" : "Ошибка сохранения"));
    } finally {
      setSaving(false);
    }
  };

  const filteredExams = exams.filter((exam) => {
    if (filterLang !== "all" && exam.language !== filterLang) return false;
    if (filterStatus !== "all" && exam.status !== filterStatus) return false;
    if (filterType !== "all" && (exam.exam_type || "full_main") !== filterType) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        exam.title.toLowerCase().includes(q) ||
        (exam.description && exam.description.toLowerCase().includes(q))
      );
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Top Banner / Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="p-1.5 rounded-lg bg-indigo-50 text-indigo-600">
              <BookOpenCheck className="w-5 h-5" />
            </span>
            <h1 className="text-xl font-bold text-slate-900">
              {lang === "ky" ? "Экзамендерди башкаруу" : "Управление Экзаменами"}
            </h1>
          </div>
          <p className="text-sm text-slate-500">
            {lang === "ky"
              ? "Canvas стилиндеги сыноо тесттерин түзүңүз, PIN-коддорду, жеткиликтүүлүк даталарын жана статусун башкарыңыз."
              : "Создавайте экзамены в стиле Canvas LMS: настраивайте статус публикации, 4-значные PIN-коды и расписание сдачи."}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchExams}
            className="p-2.5 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-xl border border-slate-200 transition"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={openCreateModal}
            className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-sm transition"
          >
            <Plus className="w-4 h-4" />
            <span>{lang === "ky" ? "Жаңы экзамен түзүү" : "Создать экзамен"}</span>
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-4 rounded-xl border border-slate-200/80">
        <div className="flex items-center gap-2 flex-1 min-w-[260px]">
          <div className="relative w-full">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder={lang === "ky" ? "Экзамендерден издөө..." : "Поиск по экзаменам..."}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Language filter */}
          <div className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
            <span>{lang === "ky" ? "Тил:" : "Язык:"}</span>
            <select
              value={filterLang}
              onChange={(e) => setFilterLang(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-800 focus:outline-none"
            >
              <option value="all">{lang === "ky" ? "Бардык тилдер" : "Все языки"}</option>
              <option value="ky">Кыргызча (KY)</option>
              <option value="ru">Русский (RU)</option>
            </select>
          </div>

          {/* Exam Type filter */}
          <div className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
            <span>{lang === "ky" ? "Түрү:" : "Тип:"}</span>
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-800 focus:outline-none"
            >
              <option value="all">{lang === "ky" ? "Бардык түрлөр" : "Все типы"}</option>
              <option value="full_main">{lang === "ky" ? "Негизги тест (Full)" : "Основной тест (Full)"}</option>
              <option value="subject">{lang === "ky" ? "Предметтик (Subject)" : "Предметный (Subject)"}</option>
              <option value="practice_bank">{lang === "ky" ? "База практики" : "База практики"}</option>
            </select>
          </div>

          {/* Status filter */}
          <div className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
            <span>{lang === "ky" ? "Статус:" : "Статус:"}</span>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-800 focus:outline-none"
            >
              <option value="all">{lang === "ky" ? "Бардыгы" : "Все"}</option>
              <option value="published">{lang === "ky" ? "Жарыяланган" : "Опубликован"}</option>
              <option value="draft">{lang === "ky" ? "Черновик" : "Черновик"}</option>
            </select>
          </div>
        </div>
      </div>

      {/* Exam Set Cards Grid */}
      {loading ? (
        <div className="flex items-center justify-center p-12 bg-white rounded-2xl border border-slate-200">
          <div className="flex flex-col items-center gap-3 text-slate-400">
            <RefreshCw className="w-6 h-6 animate-spin text-indigo-600" />
            <span className="text-sm font-medium">{t("common.loading")}</span>
          </div>
        </div>
      ) : filteredExams.length === 0 ? (
        <div className="p-12 text-center bg-white rounded-2xl border border-dashed border-slate-300">
          <BookOpenCheck className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-slate-700">
            {lang === "ky" ? "Экзамен табылган жок" : "Экзамены не найдены"}
          </h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1 mb-4">
            {lang === "ky"
              ? "Талаптарга ылайык экзамендер жок же жаңы экзамен түзө элексиз."
              : "По выбранным критериям экзамены отсутствуют. Создайте новый экзамен."}
          </p>
          <button
            onClick={openCreateModal}
            className="px-4 py-2 bg-indigo-600 text-white text-xs font-semibold rounded-lg hover:bg-indigo-700 transition"
          >
            {lang === "ky" ? "Экзамен түзүү" : "Создать экзамен"}
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredExams.map((exam) => {
            const isDraft = exam.status === "draft";
            const isLockedDates =
              exam.available_until && new Date() > new Date(exam.available_until);

            return (
              <div
                key={exam.id}
                className="bg-white rounded-2xl border border-slate-200/90 p-5 flex flex-col justify-between hover:shadow-md transition-all relative overflow-hidden"
              >
                {/* Top strip indicator */}
                <div
                  className={`absolute top-0 left-0 right-0 h-1.5 ${
                    isDraft ? "bg-amber-400" : "bg-emerald-500"
                  }`}
                />

                <div>
                  {/* Status, Language, and Completions Badges */}
                  <div className="flex items-center justify-between gap-2 mb-3 pt-1">
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => handleToggleStatus(exam)}
                        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold transition cursor-pointer ${
                          isDraft
                            ? "bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100"
                            : "bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100"
                        }`}
                        title={
                          isDraft
                            ? lang === "ky"
                              ? "Жарыялоо үчүн басыңыз"
                              : "Нажмите для публикации"
                            : lang === "ky"
                            ? "Черновик кылуу үчүн басыңыз"
                            : "Нажмите для снятия с публикации"
                        }
                      >
                        {isDraft ? (
                          <>
                            <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
                            <span>{lang === "ky" ? "Черновик" : "Черновик"}</span>
                          </>
                        ) : (
                          <>
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                            <span>{lang === "ky" ? "Жарыяланган" : "Опубликован"}</span>
                          </>
                        )}
                      </button>

                      <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase bg-slate-100 text-slate-700 border border-slate-200">
                        {exam.language?.toUpperCase() || "KY"}
                      </span>

                      {exam.exam_type === "practice_bank" ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                          {lang === "ky" ? "База машыгуу" : "База практики"}
                        </span>
                      ) : exam.exam_type === "subject" ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          {lang === "ky" ? "Предметтик" : "Предметный"}
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                          {lang === "ky" ? "Негизги ОРТ" : "Основной ОРТ"}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-1 text-xs text-slate-500 font-medium">
                      <Users className="w-3.5 h-3.5 text-indigo-500" />
                      <span>{exam.completionsCount || 0}</span>
                    </div>
                  </div>

                  {/* Title & Description */}
                  <h3 className="text-base font-bold text-slate-900 line-clamp-1 mb-1">
                    {exam.title}
                  </h3>
                  <p className="text-xs text-slate-500 line-clamp-2 min-h-[32px] mb-4">
                    {exam.description || (lang === "ky" ? "Сүрөттөмө жок" : "Без описания")}
                  </p>

                  {/* Controls / Metadata Info */}
                  <div className="bg-slate-50 rounded-xl p-3 space-y-2 border border-slate-100 text-xs">
                    {/* Access Code PIN */}
                    <div className="flex items-center justify-between text-slate-600">
                      <div className="flex items-center gap-1.5">
                        <KeyRound className="w-3.5 h-3.5 text-slate-400" />
                        <span>{lang === "ky" ? "Кирүү коду (PIN):" : "Код доступа (PIN):"}</span>
                      </div>
                      {exam.access_code ? (
                        <span className="font-mono font-bold bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded border border-indigo-200">
                          {exam.access_code}
                        </span>
                      ) : (
                        <span className="text-slate-400 font-medium">
                          {lang === "ky" ? "Жок (Ачык)" : "Без PIN"}
                        </span>
                      )}
                    </div>

                    {/* Schedule / Dates */}
                    <div className="flex items-center justify-between text-slate-600">
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5 text-slate-400" />
                        <span>{lang === "ky" ? "Мөөнөтү:" : "Сроки:"}</span>
                      </div>
                      {exam.available_from || exam.available_until ? (
                        <span className="text-[11px] text-slate-700 font-medium truncate max-w-[140px]">
                          {exam.available_until
                            ? new Date(exam.available_until).toLocaleDateString()
                            : "Ачык"}
                        </span>
                      ) : (
                        <span className="text-slate-400 font-medium">
                          {lang === "ky" ? "Чектөөсүз" : "Всегда доступен"}
                        </span>
                      )}
                    </div>

                    {/* Structure Info */}
                    <div className="flex items-center justify-between text-slate-600">
                      <div className="flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5 text-slate-400" />
                        <span>{lang === "ky" ? "Көлөмү:" : "Объем:"}</span>
                      </div>
                      <span className="font-medium text-slate-700">
                        {exam.question_count ?? exam.totalQuestions ?? 0} {lang === "ky" ? "суроо" : "вопр."} (
                        {exam.time_limit_minutes || exam.totalTimeMinutes || 170} {lang === "ky" ? "мүн" : "мин"})
                      </span>
                    </div>
                  </div>
                </div>

                {/* Card Actions */}
                <div className="pt-4 mt-4 border-t border-slate-100 flex items-center justify-between gap-2">
                  <Link
                    href={`/${lang}/exams/${exam.id}`}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-xl text-xs font-semibold transition"
                    title={lang === "ky" ? "Суроолорду көрүү" : "Просмотр вопросов"}
                  >
                    <BookOpenCheck className="w-3.5 h-3.5" />
                    <span>{lang === "ky" ? "Суроолор" : "Вопросы"} ({exam.question_count ?? exam.totalQuestions ?? 0})</span>
                  </Link>

                  <Link
                    href={`/${lang}/bulk-upload?examSetId=${exam.id}&lang=${exam.language}`}
                    className="p-2 bg-slate-100 hover:bg-indigo-50 hover:text-indigo-600 text-slate-700 rounded-xl transition"
                    title={
                      lang === "ky"
                        ? "Бул экзаменге CSV суроо жүктөө"
                        : "Загрузить вопросы в этот экзамен через CSV"
                    }
                  >
                    <UploadCloud className="w-4 h-4" />
                  </Link>

                  <button
                    onClick={() => openEditModal(exam)}
                    className="p-2 text-slate-500 hover:text-indigo-600 hover:bg-slate-100 rounded-xl transition"
                    title={lang === "ky" ? "Түзөтүү" : "Редактировать"}
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>

                  <button
                    onClick={() => handleDelete(exam.id)}
                    className="p-2 text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition"
                    title={lang === "ky" ? "Өчүрүү" : "Удалить"}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create / Edit Exam Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-white w-full max-w-lg rounded-2xl shadow-xl border border-slate-200 overflow-hidden my-8">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50/60">
              <div className="flex items-center gap-2">
                <BookOpenCheck className="w-5 h-5 text-indigo-600" />
                <h3 className="font-bold text-slate-900 text-base">
                  {editingExam
                    ? lang === "ky"
                      ? "Экзаменди өзгөртүү"
                      : "Редактировать экзамен"
                    : lang === "ky"
                    ? "Жаңы экзамен түзүү"
                    : "Создать новый экзамен"}
                </h3>
              </div>
              <button
                onClick={() => setIsModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveExam} className="p-6 space-y-4">
              {errorMsg && (
                <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{errorMsg}</span>
                </div>
              )}

              {/* Title */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {lang === "ky" ? "Экзамендин аталышы *" : "Название экзамена *"}
                </label>
                <input
                  type="text"
                  required
                  placeholder={
                    lang === "ky"
                      ? "мисалы: ОРТ Негизги Тест 2026 №1"
                      : "например: ОРТ Основной Тест 2026 №1"
                  }
                  value={formTitle}
                  onChange={(e) => setFormTitle(e.target.value)}
                  className="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {lang === "ky" ? "Сүрөттөмөсү" : "Описание"}
                </label>
                <textarea
                  rows={2}
                  placeholder={
                    lang === "ky"
                      ? "Сынактын максаты, бөлүмдөрү жөнүндө маалымат..."
                      : "Краткое описание структуры теста, указания для учащихся..."
                  }
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  className="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {/* Exam Type Selector */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {lang === "ky" ? "Экзамендин түрү *" : "Тип экзамена *"}
                </label>
                <select
                  value={formExamType}
                  onChange={(e) => setFormExamType(e.target.value as "full_main" | "subject" | "practice_bank")}
                  className="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 font-medium"
                >
                  <option value="full_main">
                    {lang === "ky" ? "ОРТ Негизги тест (Full Main Test)" : "ОРТ Основной тест (Full Main Test)"}
                  </option>
                  <option value="subject">
                    {lang === "ky" ? "Предметтик тест (Subject Test)" : "Предметный тест (Subject Test)"}
                  </option>
                  <option value="practice_bank">
                    {lang === "ky" ? "База практики (Practice Bank)" : "База практики (Practice Bank)"}
                  </option>
                </select>
                <span className="text-[11px] text-slate-400 block mt-1">
                  {formExamType === "practice_bank"
                    ? (lang === "ky" ? "Бул топтомдон суроолор ылдам машыгууда (Fast Practice) студенттерге берилет." : "Вопросы из этой базы используются для случайной генерации экспресс-тренировок.")
                    : formExamType === "subject"
                    ? (lang === "ky" ? "Өзүнчө предмет боюнча сынак (мис: Химия, Биология)." : "Тематический или предметный экзамен (напр: Химия, Биология).")
                    : (lang === "ky" ? "Стандарттуу толук ОРТ сынагы (Математика + Кыргыз тили)." : "Полноразмерный симулятор ОРТ (Математика + Русский язык).")}
                </span>
              </div>

              {/* Language & Status row */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    {lang === "ky" ? "Глобалдык тили *" : "Глобальный язык *"}
                  </label>
                  <select
                    value={formLanguage}
                    onChange={(e) => setFormLanguage(e.target.value as "ky" | "ru")}
                    className="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="ky">Кыргыз тили (KY)</option>
                    <option value="ru">Русский язык (RU)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    {lang === "ky" ? "Статус *" : "Статус публикации *"}
                  </label>
                  <select
                    value={formStatus}
                    onChange={(e) => setFormStatus(e.target.value as "draft" | "published")}
                    className="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="published">
                      {lang === "ky" ? "Жарыяланган (Published)" : "Опубликован (Published)"}
                    </option>
                    <option value="draft">
                      {lang === "ky" ? "Черновик (Draft)" : "Черновик (Draft)"}
                    </option>
                  </select>
                </div>
              </div>

              {/* Access Code PIN, Max Attempts & Time Limit */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    {lang === "ky" ? "4 орундуу PIN-код" : "4-значный PIN-код"}
                  </label>
                  <input
                    type="text"
                    maxLength={4}
                    placeholder="мис: 1234 (же бош)"
                    value={formAccessCode}
                    onChange={(e) => setFormAccessCode(e.target.value)}
                    className="w-full px-3.5 py-2 text-sm font-mono bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <span className="text-[11px] text-slate-400 block mt-0.5">
                    {lang === "ky" ? "Бош болсо - сырсөзсүз ачылат" : "Если пусто — тест без пароля"}
                  </span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    {lang === "ky" ? "Максималдуу аракети" : "Макс. количество попыток"}
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={999}
                    value={formMaxAttempts}
                    onChange={(e) => setFormMaxAttempts(Number(e.target.value))}
                    className="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <span className="text-[11px] text-slate-400 block mt-0.5">
                    {lang === "ky" ? "мис: 1 же 99 (чексиз)" : "напр: 1 или 99"}
                  </span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    {lang === "ky" ? "Убакыт чеги (мүнөт)" : "Лимит времени (минут)"}
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={360}
                    placeholder="мис: 45 же бош"
                    value={formTimeLimitMinutes}
                    onChange={(e) => setFormTimeLimitMinutes(e.target.value === "" ? "" : Number(e.target.value))}
                    className="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <span className="text-[11px] text-slate-400 block mt-0.5">
                    {lang === "ky" ? "Бош болсо - стандарттуу убакыт" : "Если пусто — стандартный таймер"}
                  </span>
                </div>
              </div>

              {/* Schedule Dates */}
              <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800">
                  <Calendar className="w-3.5 h-3.5 text-indigo-600" />
                  <span>
                    {lang === "ky" ? "Сынактын мөөнөтүн чектөө" : "Ограничение по времени сдачи"}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-medium text-slate-600 mb-1">
                      {lang === "ky" ? "Башталышы:" : "Доступен с:"}
                    </label>
                    <input
                      type="datetime-local"
                      value={formAvailableFrom}
                      onChange={(e) => setFormAvailableFrom(e.target.value)}
                      className="w-full px-2.5 py-1.5 text-xs bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-slate-600 mb-1">
                      {lang === "ky" ? "Аякташы:" : "Доступен до:"}
                    </label>
                    <input
                      type="datetime-local"
                      value={formAvailableUntil}
                      onChange={(e) => setFormAvailableUntil(e.target.value)}
                      className="w-full px-2.5 py-1.5 text-xs bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                </div>
              </div>

              {/* Submit Buttons */}
              <div className="pt-2 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition"
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-xl shadow-sm transition disabled:opacity-50 flex items-center gap-1.5"
                >
                  {saving && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>{t("common.save")}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

