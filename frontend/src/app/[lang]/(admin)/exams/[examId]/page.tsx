"use client";

import React, { useState, useEffect, use, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import { getAuthHeader } from "@/lib/api";
import { toast } from "@/components/ui/Toast";
import {
  ArrowLeft,
  BookOpenCheck,
  Plus,
  UploadCloud,
  Clock,
  KeyRound,
  Users,
  Edit3,
  Trash2,
  Calendar,
  CheckCircle2,
  AlertCircle,
  X,
  Search,
  RefreshCw,
  FileText,
  Image as ImageIcon,
  MessageSquare,
  HelpCircle,
  Compass,
} from "lucide-react";

interface ExamSetDetail {
  id: string;
  title: string;
  description?: string;
  language: string;
  exam_type?: "full_main" | "subject" | "practice_bank";
  status: "draft" | "published";
  available_from?: string | null;
  available_until?: string | null;
  access_code?: string | null;
  max_attempts: number;
  totalQuestions: number;
  totalTimeMinutes: number;
  completionsCount?: number;
  sections?: Array<{ section: string; questionCount: number; timeLimitMinutes: number }>;
}

interface QuestionItem {
  id: string;
  language: "ky" | "ru";
  section: string;
  topic: string;
  difficulty: "easy" | "medium" | "hard";
  exam_set_id?: string | null;
  stem: string;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  option_e?: string | null;
  correct_option: string;
  column_a?: string | null;
  column_b?: string | null;
  passage_text?: string | null;
  image_url?: string | null;
  explanation?: string | null;
  tags?: string[];
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

export default function ExamDeepDivePage({
  params,
}: {
  params: Promise<{ lang: string; examId: string }>;
}) {
  const unwrappedParams = use(params);
  const lang = (unwrappedParams.lang as "ky" | "ru") || "ky";
  const examId = unwrappedParams.examId;
  const { t } = useTranslation();
  const router = useRouter();

  const [exam, setExam] = useState<ExamSetDetail | null>(null);
  const [questions, setQuestions] = useState<QuestionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Filter
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSection, setSelectedSection] = useState("all");

  // Question Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingQuestion, setEditingQuestion] = useState<QuestionItem | null>(null);
  const [deletingQuestion, setDeletingQuestion] = useState<QuestionItem | null>(null);
  const [saving, setSaving] = useState(false);

  // Question Form State
  const [formSection, setFormSection] = useState("math_1");
  const [formTopic, setFormTopic] = useState("");
  const [formDifficulty, setFormDifficulty] = useState<"easy" | "medium" | "hard">("medium");
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

  const loadData = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const authHeader = await getAuthHeader();

      // 1. Fetch Exam Set details
      const examRes = await fetch(`/api/v1/exam-sets/${examId}`, { headers: authHeader });
      if (!examRes.ok) {
        throw new Error(lang === "ky" ? "Экзамен табылган жок" : "Экзаменационный сет не найден");
      }
      const examData = await examRes.json();
      setExam(examData);

      // 2. Fetch questions strictly bound to this exam
      const qRes = await fetch(`/api/v1/questions?exam_id=${examId}&limit=500`, {
        headers: authHeader,
      });
      if (qRes.ok) {
        const qData = await qRes.json();
        setQuestions(qData.items || []);
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Ката кетти");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [examId]);

  const openCreateQuestionModal = () => {
    setEditingQuestion(null);
    setFormSection(exam?.sections?.[0]?.section || "math_1");
    setFormTopic("");
    setFormDifficulty("medium");
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
    setIsModalOpen(true);
  };

  const openEditQuestionModal = (q: QuestionItem) => {
    setEditingQuestion(q);
    setFormSection(q.section);
    setFormTopic(q.topic);
    setFormDifficulty(q.difficulty);
    setFormStem(q.stem);
    setFormColumnA(q.column_a || "");
    setFormColumnB(q.column_b || "");
    setFormOptionA(q.option_a);
    setFormOptionB(q.option_b);
    setFormOptionC(q.option_c);
    setFormOptionD(q.option_d);
    setFormOptionE(q.option_e || "");
    setFormCorrectOption((q.correct_option as any) || "A");
    setFormPassageText(q.passage_text || "");
    setFormImageUrl(q.image_url || "");
    setFormExplanation(q.explanation || "");
    setFormTags(q.tags?.join(", ") || "");
    setPreviewFormula(false);
    setIsModalOpen(true);
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      setIsUploadingImage(true);
      const formData = new FormData();
      formData.append("file", file);

      const authHeader = await getAuthHeader();
      const res = await fetch("/api/v1/upload", {
        method: "POST",
        headers: authHeader,
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to upload image");
      }

      const data = await res.json();
      setFormImageUrl(data.imageUrl || data.url);
      toast.success(lang === "ky" ? "Сүрөт ийгиликтүү жүктөлдү" : "Изображение успешно загружено");
    } catch (err: any) {
      toast.error(err.message || (lang === "ky" ? "Сүрөт жүктөө катасы" : "Ошибка загрузки изображения"));
    } finally {
      setIsUploadingImage(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleSaveQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!exam) return;

    setSaving(true);
    try {
      const authHeader = await getAuthHeader();
      const payload = {
        language: exam.language,
        section: formSection,
        topic: formTopic.trim() || "General",
        difficulty: formDifficulty,
        exam_set_id: exam.id,
        stem: formStem.trim(),
        // math_1 is always comparison; "" (not null) clears columns when a question leaves math_1
        column_a: formSection === "math_1" ? formColumnA.trim() : "",
        column_b: formSection === "math_1" ? formColumnB.trim() : "",
        option_a: formOptionA.trim(),
        option_b: formOptionB.trim(),
        option_c: formOptionC.trim(),
        option_d: formOptionD.trim(),
        option_e: formOptionE.trim() || null,
        correct_option: formCorrectOption,
        passage_text: formPassageText.trim() || null,
        image_url: formImageUrl.trim() || null,
        explanation: formExplanation.trim() || null,
        tags: formTags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      };

      const url = editingQuestion
        ? `/api/v1/questions/${editingQuestion.id}`
        : "/api/v1/questions";
      const method = editingQuestion ? "PUT" : "POST";

      const res = await fetch(url, {
        method,
        headers: {
          ...authHeader,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to save question");
      }

      const savedQ = await res.json();
      if (editingQuestion) {
        setQuestions((prev) => prev.map((q) => (q.id === savedQ.id ? savedQ : q)));
      } else {
        setQuestions((prev) => [savedQ, ...prev]);
        setExam((prev) => (prev ? { ...prev, totalQuestions: (prev.totalQuestions || 0) + 1 } : null));
      }

      setIsModalOpen(false);
      await loadData();
      toast.success(
        editingQuestion
          ? (lang === "ky" ? "Суроо ийгиликтүү жаңыланды" : "Вопрос успешно обновлен")
          : (lang === "ky" ? "Жаңы суроо кошулду" : "Новый вопрос успешно добавлен")
      );
    } catch (err: any) {
      toast.error(err.message || (lang === "ky" ? "Суроону сактоо катасы" : "Ошибка сохранения вопроса"));
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteQuestion = async () => {
    if (!deletingQuestion) return;

    setSaving(true);
    try {
      const authHeader = await getAuthHeader();
      const res = await fetch(`/api/v1/questions/${deletingQuestion.id}`, {
        method: "DELETE",
        headers: authHeader,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to delete question");
      }

      const deletedId = deletingQuestion.id;
      setQuestions((prev) => prev.filter((q) => q.id !== deletedId));
      setExam((prev) => (prev ? { ...prev, totalQuestions: Math.max(0, (prev.totalQuestions || 1) - 1) } : null));
      setDeletingQuestion(null);
      await loadData();
      toast.success(lang === "ky" ? "Суроо өчүрүлдү" : "Вопрос успешно удален");
    } catch (err: any) {
      toast.error(err.message || (lang === "ky" ? "Суроону өчүрүү катасы" : "Ошибка удаления вопроса"));
    } finally {
      setSaving(false);
    }
  };

  const filteredQuestions = questions.filter((q) => {
    const matchesSection = selectedSection === "all" || q.section === selectedSection;
    const matchesSearch =
      !searchQuery ||
      q.stem.toLowerCase().includes(searchQuery.toLowerCase()) ||
      q.topic.toLowerCase().includes(searchQuery.toLowerCase()) ||
      q.id.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSection && matchesSearch;
  });

  const getExamTypeBadge = (type?: string) => {
    switch (type) {
      case "full_main":
        return {
          label: lang === "ky" ? "ОРТ Негизги тест" : "Основной тест ОРТ",
          color: "bg-blue-50 text-blue-700 border-blue-200",
        };
      case "subject":
        return {
          label: lang === "ky" ? "Предметтик тест" : "Предметный тест",
          color: "bg-purple-50 text-purple-700 border-purple-200",
        };
      case "practice_bank":
        return {
          label: lang === "ky" ? "Машыгуу базасы" : "База практики",
          color: "bg-emerald-50 text-emerald-700 border-emerald-200",
        };
      default:
        return {
          label: type || "Экзамен",
          color: "bg-slate-50 text-slate-700 border-slate-200",
        };
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-20 text-slate-400">
        <RefreshCw className="w-8 h-8 animate-spin text-indigo-600 mb-2" />
        <span className="text-sm font-medium">{t("common.loading")}</span>
      </div>
    );
  }

  if (errorMsg || !exam) {
    return (
      <div className="max-w-2xl mx-auto p-8 text-center bg-white rounded-3xl border border-slate-200 space-y-4">
        <AlertCircle className="w-12 h-12 text-rose-500 mx-auto" />
        <h3 className="text-lg font-bold text-slate-900">{errorMsg || "Экзамен табылган жок"}</h3>
        <Link
          href={`/${lang}/exams`}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-xs font-bold hover:bg-indigo-700 transition"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{lang === "ky" ? "Экзамендер тизмесине кайтуу" : "Вернуться к списку экзаменов"}</span>
        </Link>
      </div>
    );
  }

  const typeBadge = getExamTypeBadge(exam.exam_type);

  return (
    <div className="space-y-8 max-w-6xl mx-auto pb-16">
      {/* Top Breadcrumb & Navigation */}
      <div className="flex items-center justify-between">
        <Link
          href={`/${lang}/exams`}
          className="inline-flex items-center gap-2 text-xs font-bold text-slate-500 hover:text-slate-900 transition"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{lang === "ky" ? "Бардык Экзамендер" : "Все Экзаменационные Сеты"}</span>
        </Link>

        <div className="flex items-center gap-2">
          <Link
            href={`/${lang}/bulk-upload?examSetId=${exam.id}&lang=${exam.language}`}
            className="px-4 py-2 bg-white text-indigo-600 border border-indigo-200 hover:bg-indigo-50 rounded-xl text-xs font-bold shadow-xs transition flex items-center gap-1.5"
          >
            <UploadCloud className="w-4 h-4" />
            <span>{lang === "ky" ? "CSV жүктөө" : "Загрузить CSV"}</span>
          </Link>
          <button
            onClick={openCreateQuestionModal}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold shadow-xs transition flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            <span>{lang === "ky" ? "Суроо кошуу" : "Создать вопрос"}</span>
          </button>
        </div>
      </div>

      {/* Exam Metadata Hero Banner */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 shadow-xs space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`px-3 py-1 rounded-full text-xs font-bold border ${typeBadge.color}`}>
                {typeBadge.label}
              </span>
              <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-700 uppercase">
                {exam.language}
              </span>
              <span
                className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                  exam.status === "published"
                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                    : "bg-amber-50 text-amber-700 border border-amber-200"
                }`}
              >
                {exam.status === "published"
                  ? lang === "ky" ? "Жарыяланган" : "Опубликован"
                  : lang === "ky" ? "Черновик" : "Черновик"}
              </span>
              {exam.access_code && (
                <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-amber-50 text-amber-800 border border-amber-200 flex items-center gap-1 font-mono">
                  <KeyRound className="w-3.5 h-3.5" />
                  <span>PIN: {exam.access_code}</span>
                </span>
              )}
            </div>

            <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">{exam.title}</h1>
            <p className="text-xs text-slate-500 leading-relaxed max-w-3xl">
              {exam.description || (lang === "ky" ? "Сүрөттөмө берилген эмес" : "Описание отсутствует")}
            </p>
          </div>

          <div className="flex items-center gap-6 sm:flex-col sm:items-end text-right">
            <div>
              <div className="text-2xl font-black text-indigo-600">{questions.length}</div>
              <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                {lang === "ky" ? "Суроолор саны" : "Вопросов в сете"}
              </div>
            </div>
            <div>
              <div className="text-lg font-bold text-slate-700">{exam.completionsCount || 0}</div>
              <div className="text-[11px] font-medium text-slate-400">
                {lang === "ky" ? "Окуучулардын тапшыруусу" : "Сдач студентами"}
              </div>
            </div>
          </div>
        </div>

        {/* Info Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-slate-100 text-xs">
          <div className="p-3 bg-slate-50 rounded-xl">
            <span className="text-slate-400 block mb-0.5">{lang === "ky" ? "Жалпы убакыт:" : "Время сдачи:"}</span>
            <span className="font-bold text-slate-800 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-indigo-600" />
              {exam.totalTimeMinutes || 170} {lang === "ky" ? "мүнөт" : "минут"}
            </span>
          </div>
          <div className="p-3 bg-slate-50 rounded-xl">
            <span className="text-slate-400 block mb-0.5">{lang === "ky" ? "Аракеттер лимити:" : "Лимит попыток:"}</span>
            <span className="font-bold text-slate-800">
              {exam.max_attempts >= 99 ? (lang === "ky" ? "Чектөөсүз" : "Не ограничен") : `${exam.max_attempts}`}
            </span>
          </div>
          <div className="p-3 bg-slate-50 rounded-xl">
            <span className="text-slate-400 block mb-0.5">{lang === "ky" ? "Башталышы:" : "Доступен с:"}</span>
            <span className="font-bold text-slate-800">
              {exam.available_from ? new Date(exam.available_from).toLocaleDateString() : (lang === "ky" ? "Чектөөсүз" : "Сразу")}
            </span>
          </div>
          <div className="p-3 bg-slate-50 rounded-xl">
            <span className="text-slate-400 block mb-0.5">{lang === "ky" ? "Аякташы:" : "Доступен до:"}</span>
            <span className="font-bold text-slate-800">
              {exam.available_until ? new Date(exam.available_until).toLocaleDateString() : (lang === "ky" ? "Чектөөсүз" : "Бессрочно")}
            </span>
          </div>
        </div>
      </div>

      {/* Questions List & Controls */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 shadow-xs space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold text-slate-900">
              {lang === "ky" ? "Бул экзамендеги суроолор" : "Вопросы этого экзаменационного сета"}
            </h3>
            <p className="text-xs text-slate-500">
              {lang === "ky"
                ? `Бардыгы: ${filteredQuestions.length} суроо табылды (катаал байланыш)`
                : `Строгая привязка: найдено ${filteredQuestions.length} вопросов`}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Search */}
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder={lang === "ky" ? "Издөө..." : "Поиск вопросов..."}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-4 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 w-48 sm:w-60"
              />
            </div>

            {/* Section filter */}
            <select
              value={selectedSection}
              onChange={(e) => setSelectedSection(e.target.value)}
              className="px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="all">{lang === "ky" ? "Бардык бөлүмдөр" : "Все разделы"}</option>
              {SECTION_OPTIONS.map((sec) => (
                <option key={sec.value} value={sec.value}>
                  {lang === "ky" ? sec.ky : sec.ru}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Questions Table */}
        {filteredQuestions.length === 0 ? (
          <div className="p-12 text-center border-2 border-dashed border-slate-200 rounded-2xl space-y-3">
            <BookOpenCheck className="w-10 h-10 text-slate-300 mx-auto" />
            <p className="text-sm font-semibold text-slate-600">
              {lang === "ky"
                ? "Бул экзаменде азырынча суроолор жок"
                : "В этом экзаменационном сете пока нет вопросов"}
            </p>
            <p className="text-xs text-slate-400">
              {lang === "ky"
                ? "Жогорудагы «CSV жүктөө» же «Суроо кошуу» баскычы аркылуу суроолорду жүктөңүз."
                : "Воспользуйтесь кнопками «Загрузить CSV» или «Создать вопрос» для наполнения сета."}
            </p>
            <div className="pt-2 flex items-center justify-center gap-3">
              <Link
                href={`/${lang}/bulk-upload?examSetId=${exam.id}&lang=${exam.language}`}
                className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-bold shadow-xs hover:bg-indigo-700 transition"
              >
                {lang === "ky" ? "CSV аркылуу жүктөө" : "Загрузить через CSV"}
              </Link>
              <button
                onClick={openCreateQuestionModal}
                className="px-4 py-2 bg-white text-slate-700 border border-slate-200 rounded-xl text-xs font-bold hover:bg-slate-50 transition"
              >
                {lang === "ky" ? "Бирден суроо кошуу" : "Создать вручную"}
              </button>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-slate-200">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
                <tr>
                  <th className="py-3 px-4"># / ID</th>
                  <th className="py-3 px-4">{lang === "ky" ? "Бөлүм" : "Раздел"}</th>
                  <th className="py-3 px-4">{lang === "ky" ? "Тема" : "Тема"}</th>
                  <th className="py-3 px-4">{lang === "ky" ? "Деңгээл" : "Сложность"}</th>
                  <th className="py-3 px-4 min-w-[280px]">{lang === "ky" ? "Суроонун тексти" : "Текст вопроса"}</th>
                  <th className="py-3 px-4">{lang === "ky" ? "Туура жооп" : "Ответ"}</th>
                  <th className="py-3 px-4 text-right">{lang === "ky" ? "Аракеттер" : "Действия"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredQuestions.map((q, idx) => {
                  const secObj = SECTION_OPTIONS.find((s) => s.value === q.section);
                  const secLabel = secObj ? (lang === "ky" ? secObj.ky : secObj.ru) : q.section;

                  return (
                    <tr key={q.id} className="hover:bg-slate-50/70 transition">
                      <td className="py-3.5 px-4 font-mono font-bold text-slate-400">
                        {idx + 1}
                      </td>
                      <td className="py-3.5 px-4 font-bold text-slate-900 whitespace-nowrap">
                        <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-800 text-[10px] uppercase font-bold">
                          {secLabel}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-slate-600 max-w-[140px] truncate">
                        {q.topic || "General"}
                      </td>
                      <td className="py-3.5 px-4">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            q.difficulty === "easy"
                              ? "bg-emerald-50 text-emerald-700"
                              : q.difficulty === "hard"
                              ? "bg-rose-50 text-rose-700"
                              : "bg-amber-50 text-amber-700"
                          }`}
                        >
                          {q.difficulty}
                        </span>
                      </td>
                      <td className="py-3.5 px-4">
                        <div className="line-clamp-2 text-slate-900 font-medium">
                          <MathRenderer content={q.stem} />
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          {(q.column_a || q.column_b) && (
                            <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-amber-700 bg-amber-50 px-1.5 py-0.2 rounded border border-amber-200">
                              Колонка А/Б
                            </span>
                          )}
                          {q.passage_text && (
                            <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-blue-700 bg-blue-50 px-1.5 py-0.2 rounded border border-blue-200">
                              <FileText className="w-2.5 h-2.5" />
                              Passage
                            </span>
                          )}
                          {q.image_url && (
                            <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-purple-700 bg-purple-50 px-1.5 py-0.2 rounded border border-purple-200">
                              <ImageIcon className="w-2.5 h-2.5" />
                              Image
                            </span>
                          )}
                          {q.explanation && (
                            <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.2 rounded border border-emerald-200">
                              <MessageSquare className="w-2.5 h-2.5" />
                              Feedback
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3.5 px-4 font-bold text-emerald-700">
                        <span className="px-2 py-1 rounded bg-emerald-50 border border-emerald-200">
                          {q.correct_option}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => openEditQuestionModal(q)}
                            className="p-1.5 rounded-lg text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 transition"
                            title={lang === "ky" ? "Өзгөртүү" : "Редактировать"}
                          >
                            <Edit3 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => setDeletingQuestion(q)}
                            className="p-1.5 rounded-lg text-slate-500 hover:text-rose-600 hover:bg-rose-50 transition"
                            title={lang === "ky" ? "Өчүрүү" : "Удалить"}
                          >
                            <Trash2 className="w-4 h-4" />
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

      {/* Create / Edit Question Modal (ExamSet Locked) */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-xs p-4 overflow-y-auto">
          <div className="bg-white w-full max-w-2xl rounded-3xl shadow-2xl border border-slate-200 my-8 overflow-hidden">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-slate-900">
                  {editingQuestion
                    ? lang === "ky" ? "Суроону түзөтүү" : "Редактировать вопрос"
                    : lang === "ky" ? "Жаңы суроо кошуу" : "Создать новый вопрос"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {lang === "ky"
                    ? `Экзамен топтому: «${exam.title}» (${exam.language.toUpperCase()})`
                    : `Экзаменационный сет: «${exam.title}» (${exam.language.toUpperCase()})`}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveQuestion} className="p-6 space-y-4 max-h-[75vh] overflow-y-auto text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">
                    {lang === "ky" ? "Бөлүм:" : "Раздел:"}
                  </label>
                  <select
                    value={formSection}
                    onChange={(e) => setFormSection(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none font-medium"
                  >
                    {SECTION_OPTIONS.map((sec) => (
                      <option key={sec.value} value={sec.value}>
                        {lang === "ky" ? sec.ky : sec.ru}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block font-bold text-slate-700 mb-1">
                    {lang === "ky" ? "Тема:" : "Тема:"}
                  </label>
                  <input
                    type="text"
                    placeholder="мис: algebra_linear"
                    value={formTopic}
                    onChange={(e) => setFormTopic(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block font-bold text-slate-700 mb-1">
                    {lang === "ky" ? "Деңгээли:" : "Сложность:"}
                  </label>
                  <select
                    value={formDifficulty}
                    onChange={(e) => setFormDifficulty(e.target.value as any)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none font-medium"
                  >
                    <option value="easy">{lang === "ky" ? "Оңой (Easy)" : "Легкий"}</option>
                    <option value="medium">{lang === "ky" ? "Орто (Medium)" : "Средний"}</option>
                    <option value="hard">{lang === "ky" ? "Татаал (Hard)" : "Сложный"}</option>
                  </select>
                </div>
              </div>

              {/* Stem with LaTeX preview */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="font-bold text-slate-700">
                    {lang === "ky" ? "Суроонун тексти (LaTeX колдоого алынат):" : "Текст вопроса (поддержка LaTeX):"}
                  </label>
                  <button
                    type="button"
                    onClick={() => setPreviewFormula(!previewFormula)}
                    className="text-indigo-600 hover:text-indigo-800 font-semibold"
                  >
                    {previewFormula ? (lang === "ky" ? "Кодду көрүү" : "Исходный текст") : (lang === "ky" ? "LaTeX алдын ала көрүү" : "Предпросмотр LaTeX")}
                  </button>
                </div>

                {previewFormula ? (
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl min-h-[70px] text-sm text-slate-900">
                    <MathRenderer content={formStem || "..."} />
                  </div>
                ) : (
                  <textarea
                    rows={3}
                    placeholder={
                      formColumnA || formColumnB
                        ? (lang === "ky" ? "Шарт / кошумча маалымат (опционал)..." : "Условие / дополнительная информация (опционально)...")
                        : "мис: Эгер $2x + 4 = 10$ болсо, $x$ тапкыла..."
                    }
                    value={formStem}
                    onChange={(e) => setFormStem(e.target.value)}
                    className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                )}
              </div>

              {/* math_1 = Quantitative Comparison: Column A vs Column B (only shown for math_1) */}
              {formSection === "math_1" && (
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-2xl space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div>
                    <span className="font-bold text-slate-800 text-xs block">
                      {lang === "ky" ? "Сандык салыштыруу (Колонка А жана Б):" : "Количественное сравнение (Колонка А и Б):"}
                    </span>
                    <span className="text-[10px] text-slate-400">
                      {lang === "ky" ? "Эгер бул салыштыруу суроосу болсо, чоңдуктарды жазыңыз" : "Если это вопрос на сравнение, заполните величины для обеих колонок"}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      if (lang === "ky") {
                        setFormOptionA("КОЛОНКА А чоңураак");
                        setFormOptionB("КОЛОНКА Б чоңураак");
                        setFormOptionC("Эки чоңдук барабар");
                        setFormOptionD("Маалымат жетишсиз");
                      } else {
                        setFormOptionA("КОЛОНКА А больше");
                        setFormOptionB("КОЛОНКА Б больше");
                        setFormOptionC("Величины равны");
                        setFormOptionD("Недостаточно информации для определения");
                      }
                    }}
                    className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 px-2.5 py-1 rounded-lg bg-indigo-50 border border-indigo-100 transition self-start sm:self-auto cursor-pointer"
                  >
                    {lang === "ky" ? "Стандарттык жоопторду толтуруу (A-D)" : "Заполнить стандартные ответы (A-D)"}
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[10px] font-bold text-slate-500 uppercase block mb-1">
                      {lang === "ky" ? "КОЛОНКА А" : "КОЛОНКА А"}
                    </label>
                    <input
                      type="text"
                      placeholder="мис: $2x + 5$"
                      value={formColumnA}
                      onChange={(e) => setFormColumnA(e.target.value)}
                      className="w-full p-2.5 bg-white border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none text-xs text-slate-900"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] font-bold text-slate-500 uppercase block mb-1">
                      {lang === "ky" ? "КОЛОНКА Б" : "КОЛОНКА Б"}
                    </label>
                    <input
                      type="text"
                      placeholder="мис: $3x - 1$"
                      value={formColumnB}
                      onChange={(e) => setFormColumnB(e.target.value)}
                      className="w-full p-2.5 bg-white border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none text-xs text-slate-900"
                    />
                  </div>
                </div>
              </div>
              )}

              {/* Options A-D + E */}
              <div className="space-y-2">
                <label className="font-bold text-slate-700 block">
                  {lang === "ky" ? "Жооп варианттары:" : "Варианты ответов:"}
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {(["A", "B", "C", "D"] as const).map((opt) => {
                    const val =
                      opt === "A" ? formOptionA : opt === "B" ? formOptionB : opt === "C" ? formOptionC : formOptionD;
                    const setter =
                      opt === "A" ? setFormOptionA : opt === "B" ? setFormOptionB : opt === "C" ? setFormOptionC : setFormOptionD;

                    return (
                      <div key={opt} className="flex items-center gap-2 bg-slate-50 p-2 rounded-xl border border-slate-200">
                        <span className="font-mono font-bold text-slate-500 px-1">{opt}</span>
                        <input
                          type="text"
                          required={formSection !== "math_1"}
                          value={val}
                          onChange={(e) => setter(e.target.value)}
                          placeholder={`Вариант ${opt}`}
                          className="w-full bg-transparent focus:outline-none text-slate-900 text-xs"
                        />
                      </div>
                    );
                  })}
                  <div className="flex items-center gap-2 bg-slate-50 p-2 rounded-xl border border-slate-200 sm:col-span-2">
                    <span className="font-mono font-bold text-slate-500 px-1">E</span>
                    <input
                      type="text"
                      value={formOptionE}
                      onChange={(e) => setFormOptionE(e.target.value)}
                      placeholder={lang === "ky" ? "Вариант E (милдеттүү эмес)" : "Вариант E (необязательно)"}
                      className="w-full bg-transparent focus:outline-none text-slate-900 text-xs"
                    />
                  </div>
                </div>
              </div>

              {/* Correct Option */}
              <div>
                <label className="font-bold text-slate-700 block mb-1">
                  {lang === "ky" ? "Туура жооп варианты:" : "Правильный вариант:"}
                </label>
                <div className="flex gap-3">
                  {(["A", "B", "C", "D", "E"] as const).map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setFormCorrectOption(opt)}
                      className={`flex-1 py-2 rounded-xl font-bold transition text-xs ${
                        formCorrectOption === opt
                          ? "bg-emerald-600 text-white shadow-xs"
                          : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                      }`}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              </div>

              {/* Optional Rich Content: Image File Upload & Passage */}
              <div className="p-3.5 bg-slate-50 rounded-2xl border border-slate-200 space-y-3">
                <div>
                  <label className="font-bold text-slate-700 block mb-1 flex items-center justify-between">
                    <span>{lang === "ky" ? "Сүрөт / Геометриялык чийме (опционал):" : "Изображение / чертеж (опционально):"}</span>
                    {formImageUrl && (
                      <button
                        type="button"
                        onClick={() => setFormImageUrl("")}
                        className="text-rose-600 hover:underline text-[11px]"
                      >
                        {lang === "ky" ? "Өчүрүү" : "Удалить"}
                      </button>
                    )}
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="file"
                      ref={fileInputRef}
                      accept="image/*"
                      onChange={handleImageUpload}
                      className="hidden"
                    />
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isUploadingImage}
                      className="px-3.5 py-2 bg-white border border-slate-300 rounded-xl font-semibold text-slate-700 hover:bg-slate-100 transition shadow-xs flex items-center gap-1.5"
                    >
                      <ImageIcon className="w-3.5 h-3.5 text-indigo-600" />
                      <span>
                        {isUploadingImage
                          ? (lang === "ky" ? "Жүктөлүүдө..." : "Загрузка...")
                          : (lang === "ky" ? "Компьютерден жүктөө" : "Загрузить файл с устройства")}
                      </span>
                    </button>
                    {formImageUrl && (
                      <span className="text-[11px] text-emerald-700 font-semibold truncate max-w-xs">
                        ✓ {formImageUrl}
                      </span>
                    )}
                  </div>
                </div>

                <div>
                  <label className="font-bold text-slate-700 block mb-1">
                    {lang === "ky" ? "Чоң текст / Пассаж (Окуу жана түшүнүү үчүн):" : "Текст для чтения / Пассаж (опционально):"}
                  </label>
                  <textarea
                    rows={2}
                    placeholder={lang === "ky" ? "Тексттин фрагменти..." : "Фрагмент текста для анализа..."}
                    value={formPassageText}
                    onChange={(e) => setFormPassageText(e.target.value)}
                    className="w-full p-2.5 bg-white border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="font-bold text-slate-700 block mb-1">
                    {lang === "ky" ? "Түшүндүрмө (Explanation):" : "Пояснение к правильному ответу:"}
                  </label>
                  <textarea
                    rows={2}
                    placeholder={lang === "ky" ? "Эмне үчүн бул жооп туура экендигин түшүндүрүңүз..." : "Объяснение решения..."}
                    value={formExplanation}
                    onChange={(e) => setFormExplanation(e.target.value)}
                    className="w-full p-2.5 bg-white border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              {/* Modal Actions */}
              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-xl font-semibold transition"
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold shadow-xs transition disabled:opacity-50 inline-flex items-center gap-1.5 cursor-pointer"
                >
                  {saving && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>
                    {saving
                      ? (lang === "ky" ? "Сакталууда..." : "Сохранение...")
                      : (lang === "ky" ? "Сактоо" : "Сохранить")}
                  </span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingQuestion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-xs p-4">
          <div className="bg-white w-full max-w-sm rounded-2xl shadow-xl border border-slate-200 p-6 space-y-4">
            <div className="flex items-center gap-3 text-rose-600">
              <AlertCircle className="w-6 h-6 flex-shrink-0" />
              <h4 className="font-bold text-sm text-slate-900">
                {lang === "ky" ? "Суроону өчүрүү?" : "Удалить вопрос?"}
              </h4>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed">
              {lang === "ky"
                ? `Бул суроо экзамен топтомунан биротоло өчүрүлөт. Бул аракетти артка кайтаруу мүмкүн эмес.`
                : `Вопрос будет безвозвратно удален из этого экзаменационного сета.`}
            </p>
            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setDeletingQuestion(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl"
              >
                {t("common.cancel")}
              </button>
              <button
                type="button"
                onClick={handleDeleteQuestion}
                disabled={saving}
                className="px-5 py-2 bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold rounded-xl shadow-xs transition disabled:opacity-50 inline-flex items-center gap-1.5 cursor-pointer"
              >
                {saving && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>{saving ? (lang === "ky" ? "Өчүрүлүүдө..." : "Удаление...") : (lang === "ky" ? "Өчүрүү" : "Удалить")}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

