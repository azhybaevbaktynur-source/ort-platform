"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import { useTranslation } from "@/lib/i18n/context";
import {
  Users,
  Search,
  KeyRound,
  ShieldCheck,
  ShieldAlert,
  CheckCircle2,
  AlertCircle,
  X,
  RefreshCw,
  Target,
  BookOpen,
  Calendar,
  Lock,
  Unlock,
  Check,
} from "lucide-react";
import { getAuthHeader } from "@/lib/api";
import { toast } from "@/components/ui/Toast";

interface StudentItem {
  id: string;
  email: string;
  displayName: string;
  phone?: string | null;
  targetScore: number;
  createdAt?: string | null;
  grantedExamIds: string[];
}

interface ExamSet {
  id: string;
  title: string;
  description?: string;
  language: string;
  exam_type?: "full_main" | "subject" | "practice_bank";
  status: "draft" | "published";
  totalQuestions?: number;
  question_count?: number;
  time_limit_minutes?: number | null;
}

export default function StudentsManagementPage() {
  const { lang, t } = useTranslation();

  const [students, setStudents] = useState<StudentItem[]>([]);
  const [exams, setExams] = useState<ExamSet[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  // Modal State
  const [selectedStudent, setSelectedStudent] = useState<StudentItem | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [togglingExamId, setTogglingExamId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Fetch all students
  const fetchStudents = useCallback(async () => {
    try {
      const authHeader = await getAuthHeader();
      const res = await fetch("/api/v1/admin/students", {
        headers: {
          ...authHeader,
        },
      });
      if (res.ok) {
        const data = await res.json();
        setStudents(data);
      }
    } catch (err) {
      console.error("Failed to load students:", err);
    }
  }, []);

  // Fetch all exams from database
  const fetchExams = useCallback(async () => {
    try {
      const authHeader = await getAuthHeader();
      // Dynamically query all records from the exams table (ORDER BY created_at DESC)
      const res = await fetch("/api/v1/admin/exams", {
        headers: {
          ...authHeader,
        },
      });
      if (res.ok) {
        const data = await res.json();
        // Allow managing access for all exams (custom, full_main, subject)
        setExams(data as ExamSet[]);
      } else {
        // Fallback to /api/v1/exam-sets if needed
        const fallbackRes = await fetch("/api/v1/exam-sets", {
          headers: { ...authHeader },
        });
        if (fallbackRes.ok) {
          const fallbackData = await fallbackRes.json();
          setExams(fallbackData as ExamSet[]);
        }
      }
    } catch (err) {
      console.error("Failed to load exams:", err);
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchStudents(), fetchExams()]);
    setLoading(false);
  }, [fetchStudents, fetchExams]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await Promise.all([fetchStudents(), fetchExams()]);
    setRefreshing(false);
  };

  // Filter students by name or email
  const filteredStudents = useMemo(() => {
    return students.filter((s) => {
      const query = searchQuery.toLowerCase().trim();
      if (!query) return true;
      return (
        s.displayName.toLowerCase().includes(query) ||
        s.email.toLowerCase().includes(query)
      );
    });
  }, [students, searchQuery]);

  // Open modal for student
  const openAccessModal = (student: StudentItem) => {
    setSelectedStudent(student);
    setActionError(null);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedStudent(null);
    setActionError(null);
  };

  // Toggle student's access to an exam
  const handleToggleAccess = async (examId: string, currentGranted: boolean) => {
    if (!selectedStudent) return;
    setTogglingExamId(examId);
    setActionError(null);

    const nextGranted = !currentGranted;

    try {
      const authHeader = await getAuthHeader();
      const res = await fetch(`/api/v1/admin/students/${selectedStudent.id}/access`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeader,
        },
        body: JSON.stringify({
          exam_set_id: examId,
          granted: nextGranted,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to update access");
      }

      const resData = await res.json();
      const updatedExamIds: string[] = resData.grantedExamIds || [];

      // Update selectedStudent in modal
      setSelectedStudent((prev) =>
        prev ? { ...prev, grantedExamIds: updatedExamIds } : null
      );

      // Update student in main table state
      setStudents((prev) =>
        prev.map((s) =>
          s.id === selectedStudent.id
            ? { ...s, grantedExamIds: updatedExamIds }
            : s
        )
      );

      toast.success(
        nextGranted
          ? (lang === "ky" ? "Кирүү уруксаты берилди" : "Доступ к экзамену открыт")
          : (lang === "ky" ? "Кирүү уруксаты жабылды" : "Доступ к экзамену закрыт")
      );
    } catch (err: any) {
      console.error("Access toggle error:", err);
      const errMsg = err.message || (lang === "ky" ? "Ката кетти" : "Не удалось обновить доступ");
      setActionError(errMsg);
      toast.error(errMsg);
    } finally {
      setTogglingExamId(null);
    }
  };

  const formatDate = (isoString?: string | null) => {
    if (!isoString) return "—";
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(lang === "ky" ? "ky-KG" : "ru-RU", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      });
    } catch {
      return isoString;
    }
  };

  const totalAccessGrants = useMemo(() => {
    return students.reduce((acc, s) => acc + (s.grantedExamIds?.length || 0), 0);
  }, [students]);

  return (
    <div className="space-y-6 pb-12">
      {/* Top Header & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
            <Users className="w-7 h-7 text-indigo-600" />
            <span>
              {lang === "ky" ? "Окуучуларды башкаруу" : "Управление учениками"}
            </span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {lang === "ky"
              ? "Катталган окуучулардын тизмеси жана ОРТ сыноо экзамендерине жекече кирүү уруксаттары"
              : "Список зарегистрированных учеников и индивидуальное управление доступом к экзаменам"}
          </p>
        </div>

        <button
          onClick={handleRefresh}
          disabled={refreshing || loading}
          className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 rounded-xl text-xs font-semibold shadow-2xs transition cursor-pointer"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
          <span>{lang === "ky" ? "Жаңылоо" : "Обновить"}</span>
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
            <Users className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-slate-400 font-medium block">
              {lang === "ky" ? "Жалпы окуучулар" : "Всего учеников"}
            </span>
            <span className="text-2xl font-extrabold text-slate-900">
              {loading ? "..." : students.length}
            </span>
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-slate-400 font-medium block">
              {lang === "ky" ? "Берилген уруксаттар" : "Выдано доступов к тестам"}
            </span>
            <span className="text-2xl font-extrabold text-emerald-600">
              {loading ? "..." : totalAccessGrants}
            </span>
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center font-bold">
            <BookOpen className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-slate-400 font-medium block">
              {lang === "ky" ? "Жабык экзамендер (Башкарылуучу)" : "Управляемых экзаменов"}
            </span>
            <span className="text-2xl font-extrabold text-blue-600">
              {loading ? "..." : exams.length}
            </span>
          </div>
        </div>
      </div>

      {/* Search and Filters Bar */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-2xs flex flex-col sm:flex-row items-center gap-4">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={
              lang === "ky"
                ? "Аты же электрондук почтасы боюнча издөө..."
                : "Поиск по имени или email адресу..."
            }
            className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition"
          />
        </div>
        <div className="text-xs text-slate-500 font-medium whitespace-nowrap">
          {lang === "ky"
            ? `Табылды: ${filteredStudents.length}`
            : `Найдено: ${filteredStudents.length}`}
        </div>
      </div>

      {/* Students Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xs overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-slate-400 flex flex-col items-center justify-center gap-2">
            <RefreshCw className="w-6 h-6 animate-spin text-indigo-600" />
            <span className="text-xs font-medium">{t("common.loading")}</span>
          </div>
        ) : filteredStudents.length === 0 ? (
          <div className="p-12 text-center text-slate-400 flex flex-col items-center justify-center gap-2">
            <Users className="w-8 h-8 text-slate-300 stroke-[1.5]" />
            <p className="text-sm font-semibold text-slate-700">
              {lang === "ky" ? "Окуучулар табылган жок" : "Ученики не найдены"}
            </p>
            <p className="text-xs text-slate-400 max-w-sm">
              {lang === "ky"
                ? "Издөө суроо-талабы боюнча эч ким дал келбейт же системада али катталган окуучу жок."
                : "По данному запросу никто не найден или в системе пока нет зарегистрированных учеников."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/75 text-slate-500 font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">{lang === "ky" ? "Окуучу" : "Ученик"}</th>
                  <th className="py-3 px-4">{lang === "ky" ? "Email" : "Email"}</th>
                  <th className="py-3 px-4">{lang === "ky" ? "Телефон" : "Телефон"}</th>
                  <th className="py-3 px-4">{lang === "ky" ? "Максаттуу балл" : "Целевой балл"}</th>
                  <th className="py-3 px-4">{lang === "ky" ? "Кирүү уруксаттары" : "Доступы к тестам"}</th>
                  <th className="py-3 px-4">{lang === "ky" ? "Катталган күнү" : "Дата регистрации"}</th>
                  <th className="py-3 px-4 text-right">{lang === "ky" ? "Аракеттер" : "Действия"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredStudents.map((student) => {
                  const grantCount = student.grantedExamIds?.length || 0;
                  const initial = (student.displayName || student.email || "U")[0].toUpperCase();

                  return (
                    <tr
                      key={student.id}
                      className="hover:bg-slate-50/80 transition-colors"
                    >
                      {/* Name & Avatar */}
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs flex items-center justify-center shrink-0">
                            {initial}
                          </div>
                          <div>
                            <span className="font-semibold text-slate-900 block">
                              {student.displayName}
                            </span>
                            <span className="text-[10px] text-slate-400 font-mono">
                              ID: {student.id.slice(0, 10)}...
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* Email */}
                      <td className="py-3.5 px-4 font-mono text-slate-600">
                        {student.email}
                      </td>

                      {/* Phone */}
                      <td className="py-3.5 px-4 font-mono text-slate-600">
                        {student.phone ? (
                          <span className="text-slate-800 font-medium">{student.phone}</span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>

                      {/* Target Score */}
                      <td className="py-3.5 px-4">
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <Target className="w-3 h-3 text-emerald-600" />
                          <span>{student.targetScore || 200}</span>
                        </span>
                      </td>

                      {/* Granted Exams */}
                      <td className="py-3.5 px-4">
                        {grantCount > 0 ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                            <ShieldCheck className="w-3 h-3 text-indigo-600" />
                            <span>
                              {lang === "ky"
                                ? `${grantCount} экзаменге уруксат`
                                : `${grantCount} экзаменов открыто`}
                            </span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-500">
                            <Lock className="w-3 h-3 text-slate-400" />
                            <span>{lang === "ky" ? "Жабык" : "Нет доступов"}</span>
                          </span>
                        )}
                      </td>

                      {/* Registered Date */}
                      <td className="py-3.5 px-4 text-slate-500">
                        <div className="flex items-center gap-1.5">
                          <Calendar className="w-3.5 h-3.5 text-slate-400" />
                          <span>{formatDate(student.createdAt)}</span>
                        </div>
                      </td>

                      {/* Manage Access Button */}
                      <td className="py-3.5 px-4 text-right">
                        <button
                          onClick={() => openAccessModal(student)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 hover:bg-indigo-600 text-indigo-700 hover:text-white rounded-xl text-xs font-semibold border border-indigo-200 hover:border-indigo-600 transition-colors shadow-2xs cursor-pointer"
                        >
                          <KeyRound className="w-3.5 h-3.5" />
                          <span>
                            {lang === "ky" ? "Кирүү уруксаты" : "Управление доступом"}
                          </span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Access Management Modal */}
      {isModalOpen && selectedStudent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="p-6 border-b border-slate-100 flex items-start justify-between gap-4 bg-slate-50/50">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-indigo-100 text-indigo-600 flex items-center justify-center font-bold">
                  <KeyRound className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">
                    {lang === "ky" ? "Кирүү уруксаттарын башкаруу" : "Управление доступом к тестам"}
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    <span className="font-semibold text-slate-700">{selectedStudent.displayName}</span>{" "}
                    ({selectedStudent.email})
                  </p>
                </div>
              </div>
              <button
                onClick={closeModal}
                className="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-500 flex items-center justify-center transition cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Explanatory Notice */}
            <div className="px-6 py-3 bg-amber-50/70 border-b border-amber-100 text-[11px] text-amber-900 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
              <span>
                {lang === "ky"
                  ? "Практикалык базалар (practice_bank) баарына ачык. Негизги жана предметтик тесттерди бул жерден жекече күйгүзүп же өчүрө аласыз."
                  : "Банки практики (practice_bank) доступны всем автоматически. Основные и предметные экзамены открываются индивидуально переключателями ниже."}
              </span>
            </div>

            {actionError && (
              <div className="px-6 py-2.5 bg-rose-50 border-b border-rose-200 text-xs text-rose-700 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{actionError}</span>
              </div>
            )}

            {/* Exam List */}
            <div className="p-6 overflow-y-auto divide-y divide-slate-100 flex-1 space-y-1">
              {exams.length === 0 ? (
                <div className="text-center py-8 text-slate-400 text-xs">
                  {lang === "ky"
                    ? "Учурда жарыяланган негизги же предметтик экзамендер жок."
                    : "В данный момент нет опубликованных основных или предметных тестов."}
                </div>
              ) : (
                exams.map((exam) => {
                  const isGranted = (selectedStudent.grantedExamIds || []).includes(exam.id);
                  const isToggling = togglingExamId === exam.id;

                  return (
                    <div
                      key={exam.id}
                      className="py-3.5 first:pt-0 last:pb-0 flex items-center justify-between gap-4"
                    >
                      <div className="flex-1 min-w-0 pr-4">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-semibold text-slate-900 text-xs truncate">
                            {exam.title}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              (exam.exam_type === "subject" || (exam as any).type === "subject" || exam.id.toLowerCase().includes("subject"))
                                ? "bg-purple-50 text-purple-700"
                                : "bg-indigo-50 text-indigo-700"
                            }`}
                          >
                            {(exam.exam_type === "subject" || (exam as any).type === "subject" || exam.id.toLowerCase().includes("subject"))
                              ? lang === "ky"
                                ? "Предметтик"
                                : "Предметный"
                              : lang === "ky"
                              ? "Жалпы тест"
                              : "Основной тест"}
                          </span>
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 uppercase">
                            {exam.language}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          {exam.question_count ?? exam.totalQuestions ?? 0}{" "}
                          {lang === "ky" ? "суроо" : "вопросов"}
                          {exam.time_limit_minutes
                            ? ` • ${exam.time_limit_minutes} ${lang === "ky" ? "мүнөт" : "минут"}`
                            : ""}
                        </p>
                      </div>

                      {/* iOS-style toggle switch */}
                      <button
                        type="button"
                        role="switch"
                        aria-checked={isGranted}
                        disabled={isToggling}
                        onClick={() => handleToggleAccess(exam.id, isGranted)}
                        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:ring-offset-2 ${
                          isGranted ? "bg-indigo-600" : "bg-slate-200"
                        } ${isToggling ? "opacity-60 cursor-not-allowed" : ""}`}
                      >
                        <span className="sr-only">Toggle access</span>
                        <span
                          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out flex items-center justify-center ${
                            isGranted ? "translate-x-5" : "translate-x-0"
                          }`}
                        >
                          {isToggling ? (
                            <RefreshCw className="w-3 h-3 text-slate-400 animate-spin" />
                          ) : isGranted ? (
                            <Check className="w-3 h-3 text-indigo-600 stroke-[3]" />
                          ) : null}
                        </span>
                      </button>
                    </div>
                  );
                })
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
              <span className="text-xs text-slate-400">
                {lang === "ky"
                  ? `Ачык экзамендер: ${(selectedStudent.grantedExamIds || []).length} / ${exams.length}`
                  : `Открыто тестов: ${(selectedStudent.grantedExamIds || []).length} из ${exams.length}`}
              </span>
              <button
                onClick={closeModal}
                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-semibold shadow-2xs transition cursor-pointer"
              >
                {lang === "ky" ? "Даяр" : "Готово"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

