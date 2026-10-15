"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import { getAuthHeader } from "@/lib/api";
import {
  Search,
  Plus,
  UploadCloud,
  Trash2,
  Edit3,
  CheckCircle2,
  AlertCircle,
  X,
  Loader2,
  RefreshCw,
  HelpCircle,
  FileText,
  Image as ImageIcon,
  MessageSquare,
} from "lucide-react";

interface QuestionItem {
  id: string;
  language: "ky" | "ru";
  section: string;
  topic: string;
  difficulty: "easy" | "medium" | "hard";
  exam_set_id?: string | null;
  stem: string;
  column_a?: string | null;
  column_b?: string | null;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  option_e?: string | null;
  correct_option: string;
  passage_text?: string | null;
  image_url?: string | null;
  explanation?: string | null;
  tags?: string[];
  stats?: { totalAttempts?: number; correctAttempts?: number };
}

interface ExamSetOption {
  id: string;
  title: string;
  language: string;
  exam_type?: string;
}

const SECTION_OPTIONS = [
  { value: "math_1", ky: "Математика I (Салыштыруу)", ru: "Математика I (Сравнение)" },
  { value: "math_2", ky: "Математика II", ru: "Математика II" },
  { value: "reading", ky: "Окуу жана түшүнүү", ru: "Чтение и понимание" },
  { value: "analogies", ky: "Аналогиялар", ru: "Аналогии" },
  { value: "grammar", ky: "Практикалык грамматика", ru: "Практическая грамматика" },
  { value: "chemistry", ky: "Химия", ru: "Химия" },
  { value: "biology", ky: "Биология", ru: "Биология" },
  { value: "physics", ky: "Физика", ru: "Физика" },
  { value: "history", ky: "Тарых", ru: "История" },
  { value: "english", ky: "Англис тили", ru: "Английский язык" },
];

export default function QuestionBankManagerPage() {
  const { lang, t } = useTranslation();

  const [questions, setQuestions] = useState<QuestionItem[]>([]);
  const [examSets, setExamSets] = useState<ExamSetOption[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSection, setSelectedSection] = useState("all");
  const [selectedExamSet, setSelectedExamSet] = useState("all");
  const [selectedLang, setSelectedLang] = useState("all");

  // Modals state
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [editingQuestion, setEditingQuestion] = useState<QuestionItem | null>(null);
  const [deletingQuestion, setDeletingQuestion] = useState<QuestionItem | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [notification, setNotification] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // Form state (Monolingual + Rich Content)
  const [formLanguage, setFormLanguage] = useState<"ky" | "ru">("ky");
  const [formSection, setFormSection] = useState("math_1");
  const [formTopic, setFormTopic] = useState("");
  const [formDifficulty, setFormDifficulty] = useState<"easy" | "medium" | "hard">("medium");
  const [formExamSetId, setFormExamSetId] = useState("");
  const [formStem, setFormStem] = useState("");
  const [formColumnA, setFormColumnA] = useState("");
  const [formColumnB, setFormColumnB] = useState("");
  const [formOptionA, setFormOptionA] = useState("");
  const [formOptionB, setFormOptionB] = useState("");
  const [formOptionC, setFormOptionC] = useState("");
  const [formOptionD, setFormOptionD] = useState("");
  const [formOptionE, setFormOptionE] = useState("");
  const [formCorrectOption, setFormCorrectOption] = useState<"A" | "B" | "C" | "D" | "E">("A");
  const [formPassageText, setFormPassageText] = useState("");
  const [formImageUrl, setFormImageUrl] = useState("");
  const [formExplanation, setFormExplanation] = useState("");
  const [formTags, setFormTags] = useState("");
  const [previewFormula, setPreviewFormula] = useState(false);
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Fetch ExamSets for dropdown
  useEffect(() => {
    let isMounted = true;
    async function fetchExamSets() {
      try {
        const authHeader = await getAuthHeader();
        const res = await fetch("/api/v1/mock-tests/exam-sets", {
          headers: authHeader,
        });
        if (!res.ok) return;
        const data = await res.json();
        if (isMounted && Array.isArray(data)) {
          const uniqueSets: ExamSetOption[] = Array.from(
            new Map(data.map((item: any) => [item.id, item])).values()
          );
          setExamSets(uniqueSets);
        }
      } catch (err) {
        console.error("Failed to load exam sets:", err);
      }
    }
    fetchExamSets();
    return () => {
      isMounted = false;
    };
  }, []);

  const resetForm = () => {
    setFormLanguage("ky");
    setFormSection("math_1");
    setFormTopic("");
    setFormDifficulty("medium");
    setFormExamSetId("");
    setFormStem("");
    setFormColumnA("");
    setFormColumnB("");
    setFormOptionA("");
    setFormOptionB("");
    setFormOptionC("");
    setFormOptionD("");
    setFormOptionE("");
    setFormCorrectOption("A");
    setFormPassageText("");
    setFormImageUrl("");
    setFormExplanation("");
    setFormTags("");
    setPreviewFormula(false);
  };

  const populateForm = (q: QuestionItem) => {
    setFormLanguage(q.language || "ky");
    setFormSection(q.section || "math_1");
    setFormTopic(q.topic || "");
    setFormDifficulty(q.difficulty || "medium");
    setFormExamSetId(q.exam_set_id || "");
    setFormStem(q.stem || "");
    setFormColumnA(q.column_a || "");
    setFormColumnB(q.column_b || "");
    setFormOptionA(q.option_a || "");
    setFormOptionB(q.option_b || "");
    setFormOptionC(q.option_c || "");
    setFormOptionD(q.option_d || "");
    setFormOptionE(q.option_e || "");
    setFormCorrectOption((q.correct_option as "A" | "B" | "C" | "D" | "E") || "A");
    setFormPassageText(q.passage_text || "");
    setFormImageUrl(q.image_url || "");
    setFormExplanation(q.explanation || "");
    setFormTags((q.tags || []).join(", "));
  };

  const handleImageFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploadingImage(true);
    try {
      const authHeader = await getAuthHeader();
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/v1/upload", {
        method: "POST",
        headers: authHeader,
        body: formData,
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || "Image upload failed");
      }

      const data = await res.json();
      if (data.url) {
        setFormImageUrl(data.url);
        setNotification({
          type: "success",
          message: lang === "ky" ? "Сүрөт ийгиликтүү жүктөлдү" : "Изображение успешно загружено",
        });
      }
    } catch (err: any) {
      console.error("Failed to upload image:", err);
      setNotification({
        type: "error",
        message: err.message || (lang === "ky" ? "Сүрөт жүктөө катасы" : "Ошибка загрузки изображения"),
      });
    } finally {
      setIsUploadingImage(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const loadQuestions = useCallback(async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const params = new URLSearchParams();
      if (selectedSection !== "all") params.append("section", selectedSection);
      if (selectedExamSet !== "all") params.append("exam_set_id", selectedExamSet);
      if (selectedLang !== "all") params.append("language", selectedLang);
      if (searchQuery.trim()) params.append("search", searchQuery.trim());
      params.append("limit", "100");

      const authHeader = await getAuthHeader();
      const res = await fetch(`/api/v1/questions?${params.toString()}`, {
        headers: authHeader,
      });
      if (!res.ok) throw new Error("Failed to load questions");

      const data = await res.json();
      setQuestions(data.items || []);
      setTotalCount(data.total || 0);
    } catch (err: any) {
      console.error(err);
      setErrorMsg(err.message || "Failed to load questions");
    } finally {
      setIsLoading(false);
    }
  }, [selectedSection, selectedExamSet, selectedLang, searchQuery]);

  useEffect(() => {
    loadQuestions();
  }, [loadQuestions]);

  const handleOpenCreate = () => {
    resetForm();
    setEditingQuestion(null);
    setIsCreateModalOpen(true);
  };

  const handleOpenEdit = (q: QuestionItem) => {
    populateForm(q);
    setEditingQuestion(q);
    setIsCreateModalOpen(true);
  };

  const handleSaveQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    // math_1 is always quantitative comparison: Column A and Column B are required, stem/options optional
    const isComparisonSection = formSection === "math_1";
    if (isComparisonSection && (!formColumnA.trim() || !formColumnB.trim())) {
      setNotification({
        type: "error",
        message: lang === "ky" ? "Колонка А жана Колонка Б толтурулушу керек" : "Заполните Колонку А и Колонку Б",
      });
      return;
    }
    if (!isComparisonSection && !formStem.trim()) {
      setNotification({
        type: "error",
        message: lang === "ky" ? "Суроонун текстин жазыңыз" : "Укажите текст вопроса",
      });
      return;
    }

    setIsSubmitting(true);
    try {
      const tagsList = formTags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      const payload = {
        language: formLanguage,
        section: formSection,
        topic: formTopic.trim() || "General",
        difficulty: formDifficulty,
        exam_set_id: formExamSetId.trim() || null,
        stem: formStem.trim(),
        // "" (not null) clears columns when a question leaves math_1, because updates skip null fields
        column_a: isComparisonSection ? formColumnA.trim() : "",
        column_b: isComparisonSection ? formColumnB.trim() : "",
        option_a: formOptionA.trim(),
        option_b: formOptionB.trim(),
        option_c: formOptionC.trim(),
        option_d: formOptionD.trim(),
        option_e: formOptionE.trim() || null,
        correct_option: formCorrectOption,
        passage_text: formPassageText.trim() || null,
        image_url: formImageUrl.trim() || null,
        explanation: formExplanation.trim() || null,
        tags: tagsList,
      };

      const authHeader = await getAuthHeader();
      if (editingQuestion) {
        const res = await fetch(`/api/v1/questions/${editingQuestion.id}`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            ...authHeader,
          },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error("Failed to update question");

        setNotification({
          type: "success",
          message: lang === "ky" ? "Суроо өзгөртүлдү" : "Вопрос успешно обновлен",
        });
      } else {
        const res = await fetch("/api/v1/questions", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...authHeader,
          },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error("Failed to create question");

        setNotification({
          type: "success",
          message: lang === "ky" ? "Жаңы суроо кошулду" : "Вопрос успешно добавлен",
        });
      }

      setIsCreateModalOpen(false);
      resetForm();
      loadQuestions();
    } catch (err: any) {
      setNotification({
        type: "error",
        message: err.message || "Failed to save question",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deletingQuestion) return;
    setIsSubmitting(true);
    try {
      const authHeader = await getAuthHeader();
      const res = await fetch(`/api/v1/questions/${deletingQuestion.id}`, {
        method: "DELETE",
        headers: authHeader,
      });
      if (!res.ok) throw new Error("Failed to delete question");

      setNotification({
        type: "success",
        message: lang === "ky" ? "Суроо өчүрүлдү" : "Вопрос успешно удален",
      });
      setDeletingQuestion(null);
      loadQuestions();
    } catch (err: any) {
      setNotification({
        type: "error",
        message: err.message || "Failed to delete question",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {notification && (
        <div
          className={`p-4 rounded-xl text-sm flex items-center justify-between shadow-md transition-all ${
            notification.type === "success"
              ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
              : "bg-rose-50 text-rose-800 border border-rose-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {notification.type === "success" ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-600" />
            ) : (
              <AlertCircle className="w-5 h-5 text-rose-600" />
            )}
            <span>{notification.message}</span>
          </div>
          <button
            onClick={() => setNotification(null)}
            className="text-slate-400 hover:text-slate-600"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Top Banner / Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-xl font-bold text-slate-900">
            {lang === "ky" ? "Суроолор базасы" : "Банк вопросов"}
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            {lang === "ky"
              ? `Жалпы базада ${totalCount} суроо бар. Монолингвалык формат: кыргыз жана орус тилдери бөлөк сакталат.`
              : `Всего в банке: ${totalCount} вопросов. Монолингвальная структура: вопросы на кыргызском и русском изолированы.`}
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Link
            href={`/${lang}/bulk-upload`}
            className="flex items-center gap-2 px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-xl transition"
          >
            <UploadCloud className="w-4 h-4" />
            <span>{lang === "ky" ? "Массалык жүктөө" : "Массовая загрузка CSV"}</span>
          </Link>
          <button
            onClick={handleOpenCreate}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-xl shadow-sm transition"
          >
            <Plus className="w-4 h-4" />
            <span>{lang === "ky" ? "Суроо түзүү" : "Создать вопрос"}</span>
          </button>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 flex flex-wrap items-center justify-between gap-4">
        {/* Search */}
        <div className="relative flex-1 min-w-[240px]">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder={
              lang === "ky" ? "Суроонун тексти же темасы боюнча издөө..." : "Поиск по тексту или теме..."
            }
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div className="flex items-center gap-3">
          {/* Language filter */}
          <div className="flex items-center gap-1.5 text-xs text-slate-600">
            <span>{lang === "ky" ? "Тил:" : "Язык:"}</span>
            <select
              value={selectedLang}
              onChange={(e) => setSelectedLang(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 text-xs text-slate-800 focus:outline-none"
            >
              <option value="all">{lang === "ky" ? "Бардыгы" : "Все"}</option>
              <option value="ky">Кыргызча (KY)</option>
              <option value="ru">Русский (RU)</option>
            </select>
          </div>

          {/* Section filter */}
          <div className="flex items-center gap-1.5 text-xs text-slate-600">
            <span>{lang === "ky" ? "Бөлүм:" : "Раздел:"}</span>
            <select
              value={selectedSection}
              onChange={(e) => setSelectedSection(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 text-xs text-slate-800 focus:outline-none"
            >
              <option value="all">{lang === "ky" ? "Бардык бөлүмдөр" : "Все разделы"}</option>
              {SECTION_OPTIONS.map((sec) => (
                <option key={sec.value} value={sec.value}>
                  {lang === "ky" ? sec.ky : sec.ru}
                </option>
              ))}
            </select>
          </div>

          {/* ExamSet filter */}
          <div className="flex items-center gap-1.5 text-xs text-slate-600">
            <span>{lang === "ky" ? "Сет:" : "Сет:"}</span>
            <select
              value={selectedExamSet}
              onChange={(e) => setSelectedExamSet(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 text-xs text-slate-800 focus:outline-none max-w-[150px] truncate"
            >
              <option value="all">{lang === "ky" ? "Бардык сеттер" : "Все сеты"}</option>
              {examSets.map((es) => (
                <option key={es.id} value={es.id}>
                  [{es.exam_type || "set"}] {es.title}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={loadQuestions}
            className="p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Questions Table */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="p-12 flex flex-col items-center justify-center gap-2 text-slate-400">
            <Loader2 className="w-6 h-6 animate-spin text-indigo-600" />
            <span className="text-xs">{t("common.loading")}</span>
          </div>
        ) : questions.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            <HelpCircle className="w-10 h-10 text-slate-300 mx-auto mb-2" />
            <p className="text-sm font-semibold">
              {lang === "ky" ? "Суроолор табылган жок" : "Вопросы не найдены"}
            </p>
            <p className="text-xs text-slate-400 mt-1">
              {lang === "ky"
                ? "Издөө шарттарын өзгөртүңүз же жаңы суроо кошуңуз"
                : "Попробуйте изменить фильтры или добавьте новый вопрос"}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider text-[10px]">
                  <th className="py-3 px-4 w-14">Тил</th>
                  <th className="py-3 px-4 w-28">Бөлүм</th>
                  <th className="py-3 px-4 w-32">Тема / Topic</th>
                  <th className="py-3 px-4">Суроонун тексти (Stem)</th>
                  <th className="py-3 px-4 w-24 text-center">Туурасы</th>
                  <th className="py-3 px-4 w-28 text-center">Кошумча</th>
                  <th className="py-3 px-4 w-32 text-center">{lang === "ky" ? "Экзамен топтому" : "Экзаменационный сет"}</th>
                  <th className="py-3 px-4 w-24 text-right">Аракеттер</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {questions.map((q) => {
                  const hasFeedback = Boolean(q.explanation && q.explanation.trim());
                  const hasPassage = Boolean(q.passage_text && q.passage_text.trim());
                  const hasImage = Boolean(q.image_url && q.image_url.trim());

                  return (
                    <tr key={q.id} className="hover:bg-slate-50/80 transition-colors">
                      {/* Language */}
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded font-bold uppercase text-[10px] bg-slate-100 text-slate-700 border border-slate-200">
                          {q.language?.toUpperCase() || "KY"}
                        </span>
                      </td>

                      {/* Section */}
                      <td className="py-3 px-4 font-medium text-slate-700">
                        <span className="truncate block max-w-[100px]">{q.section}</span>
                      </td>

                      {/* Topic */}
                      <td className="py-3 px-4">
                        <span className="font-medium text-slate-800 bg-slate-100 px-2 py-0.5 rounded text-[11px] block truncate max-w-[120px]">
                          {q.topic || "General"}
                        </span>
                      </td>

                      {/* Question Stem */}
                      <td className="py-3 px-4 text-slate-800 max-w-md">
                        <div className="line-clamp-2">
                          <MathRenderer content={q.stem} />
                        </div>
                      </td>

                      {/* Correct Option */}
                      <td className="py-3 px-4 text-center">
                        <span className="font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-md text-xs">
                          {q.correct_option}
                        </span>
                      </td>

                      {/* Extra Badges: Feedback / Passage / Image */}
                      <td className="py-3 px-4 text-center">
                        <div className="flex items-center justify-center gap-1">
                          {hasFeedback && (
                            <span
                              className="p-1 rounded bg-indigo-50 text-indigo-700 border border-indigo-200"
                              title={q.explanation || "Has Feedback"}
                            >
                              <MessageSquare className="w-3.5 h-3.5" />
                            </span>
                          )}
                          {hasPassage && (
                            <span
                              className="p-1 rounded bg-blue-50 text-blue-700 border border-blue-200"
                              title="Reading Passage attached"
                            >
                              <FileText className="w-3.5 h-3.5" />
                            </span>
                          )}
                          {hasImage && (
                            <span
                              className="p-1 rounded bg-purple-50 text-purple-700 border border-purple-200"
                              title="Diagram Image attached"
                            >
                              <ImageIcon className="w-3.5 h-3.5" />
                            </span>
                          )}
                          {!hasFeedback && !hasPassage && !hasImage && (
                            <span className="text-slate-300">—</span>
                          )}
                        </div>
                      </td>

                      {/* ExamSet */}
                      <td className="py-3 px-4 text-center">
                        {q.exam_set_id ? (
                          <span
                            className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 inline-block max-w-[120px] truncate align-middle"
                            title={examSets.find((es) => es.id === q.exam_set_id)?.title || q.exam_set_id}
                          >
                            {examSets.find((es) => es.id === q.exam_set_id)?.title || q.exam_set_id}
                          </span>
                        ) : (
                          <span className="text-slate-300 text-xs">—</span>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleOpenEdit(q)}
                            className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition"
                            title="Edit"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => setDeletingQuestion(q)}
                            className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                            title="Delete"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create / Edit Question Modal */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-white w-full max-w-2xl rounded-2xl shadow-xl border border-slate-200 overflow-hidden my-8">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50/70">
              <h3 className="font-bold text-slate-900 text-base">
                {editingQuestion
                  ? lang === "ky"
                    ? "Суроону түзөтүү"
                    : "Редактировать вопрос"
                  : lang === "ky"
                  ? "Жаңы суроо кошуу"
                  : "Добавить новый вопрос"}
              </h3>
              <button
                onClick={() => setIsCreateModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveQuestion} className="p-6 space-y-4 max-h-[80vh] overflow-y-auto">
              {/* Language, Section, Topic Row */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {/* Language */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    {lang === "ky" ? "Тили *" : "Язык *"}
                  </label>
                  <select
                    value={formLanguage}
                    onChange={(e) => setFormLanguage(e.target.value as "ky" | "ru")}
                    className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="ky">Кыргызча (KY)</option>
                    <option value="ru">Русский (RU)</option>
                  </select>
                </div>

                {/* Section */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    {lang === "ky" ? "Бөлүм *" : "Раздел *"}
                  </label>
                  <select
                    value={formSection}
                    onChange={(e) => setFormSection(e.target.value)}
                    className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    {SECTION_OPTIONS.map((sec) => (
                      <option key={sec.value} value={sec.value}>
                        {lang === "ky" ? sec.ky : sec.ru}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Topic */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    {lang === "ky" ? "Тема *" : "Тема *"}
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="мис: algebra_linear"
                    value={formTopic}
                    onChange={(e) => setFormTopic(e.target.value)}
                    className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>

              {/* Difficulty and ExamSet Link */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    {lang === "ky" ? "Татаалдыгы" : "Сложность"}
                  </label>
                  <select
                    value={formDifficulty}
                    onChange={(e) => setFormDifficulty(e.target.value as any)}
                    className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="easy">{lang === "ky" ? "Оңой" : "Легкий"}</option>
                    <option value="medium">{lang === "ky" ? "Орто" : "Средний"}</option>
                    <option value="hard">{lang === "ky" ? "Татаал" : "Сложный"}</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    {lang === "ky" ? "Экзамен топтому (ExamSet)" : "Экзаменационный сет (ExamSet)"}
                  </label>
                  <select
                    value={formExamSetId}
                    onChange={(e) => setFormExamSetId(e.target.value)}
                    className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">{lang === "ky" ? "— Байланбаган —" : "— Без привязки —"}</option>
                    {examSets
                      .filter((e) => e.language === formLanguage)
                      .map((es) => (
                        <option key={es.id} value={es.id}>
                          [{es.exam_type || "set"}] {es.title}
                        </option>
                      ))}
                  </select>
                </div>
              </div>

              {/* Reading Passage Text (Optional) */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-blue-600" />
                  <span>{lang === "ky" ? "Окуу тексти (Passage Text - Опционалдуу)" : "Текст для чтения (Passage Text - Опционально)"}</span>
                </label>
                <textarea
                  rows={3}
                  placeholder={
                    lang === "ky"
                      ? "Чоң окуу тексти (Reading Comprehension бөлүмү үчүн)..."
                      : "Текст для секции Чтение и понимание..."
                  }
                  value={formPassageText}
                  onChange={(e) => setFormPassageText(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {/* Geometry Diagram / Image Upload (Local File Upload) */}
              <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3.5 space-y-2">
                <label className="block text-xs font-semibold text-slate-700 flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <ImageIcon className="w-3.5 h-3.5 text-purple-600" />
                    <span>{lang === "ky" ? "Сүрөт жүктөө (Геометрия / Схема)" : "Загрузка изображения (Геометрия / Схема)"}</span>
                  </span>
                  {formImageUrl && (
                    <button
                      type="button"
                      onClick={() => setFormImageUrl("")}
                      className="text-[11px] text-rose-600 hover:text-rose-700 font-medium flex items-center gap-1"
                    >
                      <Trash2 className="w-3 h-3" />
                      {lang === "ky" ? "Өчүрүү" : "Удалить"}
                    </button>
                  )}
                </label>

                <input
                  type="file"
                  ref={fileInputRef}
                  accept="image/*"
                  onChange={handleImageFileUpload}
                  className="hidden"
                />

                {formImageUrl ? (
                  <div className="flex items-center gap-3 bg-white p-2 rounded-lg border border-slate-200">
                    <img
                      src={formImageUrl}
                      alt="Uploaded diagram"
                      className="w-16 h-16 object-contain rounded border border-slate-100 bg-slate-50"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-mono text-slate-600 truncate">{formImageUrl}</p>
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={isUploadingImage}
                        className="mt-1 text-[11px] text-indigo-600 hover:text-indigo-700 font-medium"
                      >
                        {lang === "ky" ? "Башка сүрөт тандоо" : "Заменить файл"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isUploadingImage}
                    className="w-full flex items-center justify-center gap-2 py-2.5 px-3 border border-dashed border-slate-300 rounded-lg bg-white hover:bg-slate-50 text-xs text-slate-600 transition"
                  >
                    {isUploadingImage ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
                        <span>{lang === "ky" ? "Жүктөлүүдө..." : "Загрузка..."}</span>
                      </>
                    ) : (
                      <>
                        <UploadCloud className="w-4 h-4 text-slate-400" />
                        <span>{lang === "ky" ? "Компьютерден сүрөт тандоо (PNG, JPG, SVG)" : "Выбрать изображение с компьютера (PNG, JPG, SVG)"}</span>
                      </>
                    )}
                  </button>
                )}
              </div>

              {/* Question Stem */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-slate-700">
                    {lang === "ky" ? "Суроонун тексти (Stem) *" : "Текст вопроса (Stem) *"}
                  </label>
                  <button
                    type="button"
                    onClick={() => setPreviewFormula(!previewFormula)}
                    className="text-[11px] text-indigo-600 font-medium hover:underline"
                  >
                    {previewFormula ? "Жазуу" : "LaTeX формуласын көрүү"}
                  </button>
                </div>
                <textarea
                  rows={3}
                  required={formSection !== "math_1"}
                  placeholder="Суроонун мазмуну (LaTeX формулаларын $...$ ичинде жазса болот)"
                  value={formStem}
                  onChange={(e) => setFormStem(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                />
                {previewFormula && formStem && (
                  <div className="p-3 bg-slate-100 rounded-lg text-xs mt-1 border border-slate-200">
                    <MathRenderer content={formStem} />
                  </div>
                )}
              </div>

              {/* math_1 = Quantitative comparison: Column A vs Column B */}
              {formSection === "math_1" && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">КОЛОНКА А *</label>
                    <input
                      type="text"
                      required
                      placeholder={lang === "ky" ? "мис: $2x + 5$" : "напр.: $2x + 5$"}
                      value={formColumnA}
                      onChange={(e) => setFormColumnA(e.target.value)}
                      className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">КОЛОНКА Б *</label>
                    <input
                      type="text"
                      required
                      placeholder={lang === "ky" ? "мис: $3x - 1$" : "напр.: $3x - 1$"}
                      value={formColumnB}
                      onChange={(e) => setFormColumnB(e.target.value)}
                      className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                    />
                  </div>
                </div>
              )}

              {/* Options A, B, C, D */}
              <div className="space-y-2">
                <label className="block text-xs font-semibold text-slate-700">
                  {lang === "ky" ? "Жооп варианттары *" : "Варианты ответов *"}
                </label>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <div className="flex items-center gap-2">
                    <span className="w-6 h-6 rounded bg-slate-200 flex items-center justify-center font-bold text-xs text-slate-700">
                      A
                    </span>
                    <input
                      type="text"
                      required={formSection !== "math_1"}
                      placeholder="Вариант A"
                      value={formOptionA}
                      onChange={(e) => setFormOptionA(e.target.value)}
                      className="flex-1 px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-6 h-6 rounded bg-slate-200 flex items-center justify-center font-bold text-xs text-slate-700">
                      B
                    </span>
                    <input
                      type="text"
                      required={formSection !== "math_1"}
                      placeholder="Вариант B"
                      value={formOptionB}
                      onChange={(e) => setFormOptionB(e.target.value)}
                      className="flex-1 px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-6 h-6 rounded bg-slate-200 flex items-center justify-center font-bold text-xs text-slate-700">
                      C
                    </span>
                    <input
                      type="text"
                      required={formSection !== "math_1"}
                      placeholder="Вариант C"
                      value={formOptionC}
                      onChange={(e) => setFormOptionC(e.target.value)}
                      className="flex-1 px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-6 h-6 rounded bg-slate-200 flex items-center justify-center font-bold text-xs text-slate-700">
                      D
                    </span>
                    <input
                      type="text"
                      required={formSection !== "math_1"}
                      placeholder="Вариант D"
                      value={formOptionD}
                      onChange={(e) => setFormOptionD(e.target.value)}
                      className="flex-1 px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                  <div className="flex items-center gap-2 md:col-span-2">
                    <span className="w-6 h-6 rounded bg-slate-200 flex items-center justify-center font-bold text-xs text-slate-700">
                      E
                    </span>
                    <input
                      type="text"
                      placeholder={lang === "ky" ? "Вариант E (милдеттүү эмес)" : "Вариант E (необязательно)"}
                      value={formOptionE}
                      onChange={(e) => setFormOptionE(e.target.value)}
                      className="flex-1 px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                </div>
              </div>

              {/* Correct Option Selector */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {lang === "ky" ? "Туура жоопту тандаңыз *" : "Выберите правильный ответ *"}
                </label>
                <div className="flex gap-3">
                  {(["A", "B", "C", "D", "E"] as const).map((opt) => (
                    <label
                      key={opt}
                      className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-xl border text-xs font-bold cursor-pointer transition ${
                        formCorrectOption === opt
                          ? "bg-emerald-600 text-white border-emerald-600 shadow-sm"
                          : "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100"
                      }`}
                    >
                      <input
                        type="radio"
                        name="correct_option"
                        value={opt}
                        checked={formCorrectOption === opt}
                        onChange={() => setFormCorrectOption(opt)}
                        className="hidden"
                      />
                      <span>{opt}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Explanation (Feedback) */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {lang === "ky" ? "Түшүндүрмө / Feedback (Опционалдуу)" : "Пояснение / Feedback (Опционально)"}
                </label>
                <textarea
                  rows={2}
                  placeholder="Окуучу ката кетиргенде чыгуучу түшүндүрмө..."
                  value={formExplanation}
                  onChange={(e) => setFormExplanation(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {/* Tags */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {lang === "ky" ? "Тегдер (үтүр менен)" : "Теги (через запятую)"}
                </label>
                <input
                  type="text"
                  placeholder="math, geometry, ort_2026"
                  value={formTags}
                  onChange={(e) => setFormTags(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {/* Form Actions */}
              <div className="pt-3 border-t border-slate-200 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition"
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-xl shadow-sm transition disabled:opacity-50 flex items-center gap-1.5"
                >
                  {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>{t("common.save")}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingQuestion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-sm p-4">
          <div className="bg-white w-full max-w-md rounded-2xl shadow-xl border border-slate-200 p-6 space-y-4">
            <div className="flex items-center gap-3 text-rose-600">
              <div className="w-10 h-10 rounded-full bg-rose-50 flex items-center justify-center">
                <Trash2 className="w-5 h-5" />
              </div>
              <h3 className="font-bold text-slate-900 text-base">
                {lang === "ky" ? "Суроону өчүрүү" : "Удаление вопроса"}
              </h3>
            </div>
            <p className="text-xs text-slate-600">
              {lang === "ky"
                ? "Бул суроону базадан өчүрүүнү каалайсызбы? Бул аракетти артка кайтарууга болбойт."
                : "Вы действительно хотите удалить этот вопрос из базы? Это действие необратимо."}
            </p>
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setDeletingQuestion(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={handleDeleteConfirm}
                disabled={isSubmitting}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold rounded-xl shadow-sm transition disabled:opacity-50"
              >
                {lang === "ky" ? "Өчүрүү" : "Удалить"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
