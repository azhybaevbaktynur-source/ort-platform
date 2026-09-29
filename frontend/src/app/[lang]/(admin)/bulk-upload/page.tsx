"use client";

import React, { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import {
  UploadCloud,
  CheckCircle2,
  AlertCircle,
  FileText,
  ArrowRight,
  Database,
  Layers,
  BookOpen,
  Sparkles,
  BookOpenCheck,
  Globe,
  RefreshCw,
} from "lucide-react";
import { getAuthHeader } from "@/lib/api";

interface ExamSetSummary {
  id: string;
  title: string;
  language: string;
  status: string;
  exam_type?: string;
}

function BulkUploadContent() {
  const { lang, t } = useTranslation();
  const searchParams = useSearchParams();
  const preselectedExamSetId = searchParams.get("examSetId");
  const preselectedLang = searchParams.get("lang") as "ky" | "ru" | null;

  const [file, setFile] = useState<File | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadComplete, setUploadComplete] = useState(false);

  // 1. Global Language Selection (Cascades to all questions)
  const [selectedLanguage, setSelectedLanguage] = useState<"ky" | "ru">(preselectedLang || "ky");

  // 2. ExamSet Selection & Creation
  const [examSets, setExamSets] = useState<ExamSetSummary[]>([]);
  const [isCreatingNewSet, setIsCreatingNewSet] = useState(!preselectedExamSetId);
  const [selectedExamSetId, setSelectedExamSetId] = useState<string>(preselectedExamSetId || "");
  const [newExamTitle, setNewExamTitle] = useState("");
  const [newExamType, setNewExamType] = useState<"full_main" | "subject" | "practice_bank">("full_main");
  const [createdExamSetId, setCreatedExamSetId] = useState<string | null>(null);

  // 3. Validation report state
  const [report, setReport] = useState<{
    totalRows: number;
    validRowsCount: number;
    invalidRowsCount: number;
    errors: Array<{ rowNumber: number; field: string; errorMessage: string }>;
    preview: Array<{
      section: string;
      stem: string;
      correct_option: string;
      passage_text?: string;
      image_url?: string;
    }>;
  } | null>(null);

  useEffect(() => {
    let isMounted = true;
    async function loadSets() {
      try {
        const authHeader = await getAuthHeader();
        const res = await fetch("/api/v1/exam-sets", {
          headers: authHeader,
        });
        if (!res.ok) return;
        const data = await res.json();
        if (isMounted && Array.isArray(data)) {
          // Deduplicate by ID to guarantee unique React keys
          const uniqueSets: ExamSetSummary[] = Array.from(
            new Map(data.map((item: any) => [item.id, item])).values()
          );
          setExamSets(uniqueSets);
          if (preselectedExamSetId) {
            const found = uniqueSets.find((e) => e.id === preselectedExamSetId);
            if (found) {
              setSelectedExamSetId(found.id);
              if (found.language === "ky" || found.language === "ru") {
                setSelectedLanguage(found.language);
              }
              setIsCreatingNewSet(false);
            }
          }
        }
      } catch (err) {
        console.error("Failed to load exam sets:", err);
      }
    }
    loadSets();
    return () => {
      isMounted = false;
    };
  }, [preselectedExamSetId]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setReport(null);
      setUploadComplete(false);
    }
  };

  const handleValidate = async () => {
    if (!file) return;
    setIsValidating(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("language", selectedLanguage);
      if (selectedExamSetId) {
        formData.append("exam_id", selectedExamSetId);
        formData.append("exam_set_id", selectedExamSetId);
      }

      const authHeader = await getAuthHeader();
      const res = await fetch("/api/v1/bulk/validate-csv", {
        method: "POST",
        headers: authHeader,
        body: formData,
      });

      if (!res.ok) {
        let msg = "Validation failed";
        try {
          const text = await res.text();
          try {
            const err = JSON.parse(text);
            msg = err.detail || err.message || msg;
          } catch {
            msg = text || msg;
          }
        } catch {
          // ignore
        }
        throw new Error(msg);
      }

      const data = await res.json();
      setReport({
        totalRows: data.totalRows,
        validRowsCount: data.validRowsCount,
        invalidRowsCount: data.invalidRowsCount,
        errors: data.errors || [],
        preview: (data.previewQuestions || []).map((q: any) => ({
          section: q.section,
          stem: q.stem || "",
          correct_option: q.correct_option || "A",
          passage_text: q.passage_text,
          image_url: q.image_url,
        })),
      });
    } catch (err: any) {
      alert(err.message || "Failed to validate CSV");
    } finally {
      setIsValidating(false);
    }
  };

  const handleCommitBatch = async () => {
    if (!file) return;
    if (!isCreatingNewSet && !selectedExamSetId) {
      alert(lang === "ky" ? "Сураныч, экзамен топтомун тандаңыз!" : "Пожалуйста, выберите экзаменационный сет!");
      return;
    }
    if (isCreatingNewSet && !newExamTitle.trim()) {
      alert(lang === "ky" ? "Сураныч, жаңы экзамендин аталышын жазыңыз!" : "Пожалуйста, укажите название нового экзамена!");
      return;
    }

    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("language", selectedLanguage);

      if (!isCreatingNewSet && selectedExamSetId) {
        formData.append("exam_id", selectedExamSetId);
        formData.append("exam_set_id", selectedExamSetId);
      } else if (isCreatingNewSet && newExamTitle.trim()) {
        formData.append("mock_test_title", newExamTitle.trim());
        formData.append("exam_type", newExamType);
      }

      const authHeader = await getAuthHeader();
      const res = await fetch("/api/v1/bulk/upload-csv", {
        method: "POST",
        headers: authHeader,
        body: formData,
      });

      if (!res.ok) {
        let msg = "Upload failed";
        try {
          const text = await res.text();
          try {
            const err = JSON.parse(text);
            msg = err.detail || err.message || msg;
          } catch {
            msg = text || msg;
          }
        } catch {
          // ignore
        }
        throw new Error(msg);
      }

      const data = await res.json();
      const targetId = data.examSetId || data.createdTemplateId || selectedExamSetId;
      if (targetId) {
        setCreatedExamSetId(targetId);
      }
      setUploadComplete(true);
    } catch (err: any) {
      alert(err.message || "Failed to upload CSV");
    } finally {
      setIsUploading(false);
    }
  };

  const getExamTypeLabel = (type?: string) => {
    switch (type) {
      case "full_main":
        return lang === "ky" ? "ОРТ Негизги тест" : "Основной тест ОРТ";
      case "subject":
        return lang === "ky" ? "Предметтик тест" : "Предметный тест";
      case "practice_bank":
        return lang === "ky" ? "Машыгуу базасы" : "База практики";
      default:
        return type || "";
    }
  };

  return (
    <div className="space-y-8 max-w-4xl mx-auto pb-12">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-slate-900 tracking-tight">
          {t("instructor.uploadTitle")}
        </h2>
        <p className="text-sm text-slate-500 mt-1">
          {lang === "ky"
            ? "CSV аркылуу суроолорду топтому менен текшерип, тандалган Экзамен топтомуна түз жүктөңүз."
            : "Линейная загрузка базы вопросов через CSV с авто-каскадированием языка и привязкой к экзаменационным сетам."}
        </p>
      </div>

      {/* STEP 1: Global Language Selection */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-7 shadow-xs space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-xs font-bold text-indigo-600 uppercase tracking-wider block">
              {lang === "ky" ? "1-Кадам: Экзамен Тили" : "Шаг 1: Язык экзамена"}
            </span>
            <h3 className="text-base font-bold text-slate-900 mt-0.5">
              {lang === "ky" ? "Суроолордун тилин тандаңыз" : "Выберите язык загружаемых вопросов"}
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSelectedLanguage("ky")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
                selectedLanguage === "ky"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "bg-slate-50 text-slate-700 border border-slate-200 hover:bg-slate-100"
              }`}
            >
              <Globe className="w-3.5 h-3.5" />
              Кыргызча (KY)
            </button>
            <button
              type="button"
              onClick={() => setSelectedLanguage("ru")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
                selectedLanguage === "ru"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "bg-slate-50 text-slate-700 border border-slate-200 hover:bg-slate-100"
              }`}
            >
              <Globe className="w-3.5 h-3.5" />
              Русский (RU)
            </button>
          </div>
        </div>
        <p className="text-xs text-slate-500">
          {lang === "ky"
            ? "CSV файлынын ичинде 'language' тилкеси кереги жок. Бардык суроолорго бул тил автоматтык түрдө ыйгарылат."
            : "Колонка языка внутри CSV не требуется. Все вопросы будут созданы на выбранном языке."}
        </p>
      </div>

      {/* STEP 2: Destination ExamSet Selection */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-7 shadow-xs space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-xs font-bold text-indigo-600 uppercase tracking-wider block">
              {lang === "ky" ? "2-Кадам: Экзамен топтому (ExamSet)" : "Шаг 2: Экзаменационный сет (ExamSet)"}
            </span>
            <h3 className="text-base font-bold text-slate-900 mt-0.5">
              {lang === "ky" ? "Суроолор кайсы экзаменге бекитилсин?" : "К какому экзамену привязать вопросы?"}
            </h3>
          </div>

          <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-xl">
            <button
              type="button"
              onClick={() => setIsCreatingNewSet(false)}
              className={`text-xs px-3 py-1.5 rounded-lg font-semibold transition ${
                !isCreatingNewSet
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {lang === "ky" ? "Бар болгон топтом" : "Существующий сет"}
            </button>
            <button
              type="button"
              onClick={() => setIsCreatingNewSet(true)}
              className={`text-xs px-3 py-1.5 rounded-lg font-semibold transition ${
                isCreatingNewSet
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {lang === "ky" ? "Жаңы экзамен түзүү" : "Создать новый сет"}
            </button>
          </div>
        </div>

        {!isCreatingNewSet ? (
          <div className="space-y-2">
            <label className="block text-xs font-bold text-slate-700">
              {lang === "ky" ? "Экзаменди тандаңыз:" : "Выберите экзамен из списка:"}
            </label>
            <select
              value={selectedExamSetId}
              onChange={(e) => setSelectedExamSetId(e.target.value)}
              className="w-full px-4 py-2.5 text-sm bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 font-medium"
            >
              <option value="">
                {lang === "ky" ? "-- Экзамен топтомун тандаңыз --" : "-- Выберите экзаменационный сет --"}
              </option>
              {examSets
                .filter((e) => e.language === selectedLanguage)
                .map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.title} [{getExamTypeLabel(e.exam_type)}] ({e.status})
                  </option>
                ))}
            </select>
          </div>
        ) : (
          <div className="space-y-4 p-4 bg-indigo-50/40 rounded-2xl border border-indigo-100">
            <div>
              <label className="block text-xs font-bold text-slate-800 mb-1">
                {lang === "ky" ? "Жаңы экзамендин аталышы:" : "Название нового экзаменационного сета:"}
              </label>
              <input
                type="text"
                placeholder={
                  lang === "ky"
                    ? "мис: ОРТ 2026 Негизги Тест №2 же Биология боюнча машыгуу"
                    : "напр: ОРТ 2026 Основной Тест №2 или Тренировочная база биологии"
                }
                value={newExamTitle}
                onChange={(e) => setNewExamTitle(e.target.value)}
                className="w-full px-4 py-2.5 text-sm bg-white border border-indigo-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-800 mb-2">
                {lang === "ky" ? "Экзамендин түрү (Exam Type):" : "Тип экзаменационного сета:"}
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                {[
                  {
                    id: "full_main",
                    titleKy: "ОРТ Негизги тест",
                    titleRu: "Основной тест ОРТ",
                    descKy: "150 суроо, стандарттык бөлүмдөр",
                    descRu: "150 вопросов, стандартные модули",
                  },
                  {
                    id: "subject",
                    titleKy: "Предметтик тест",
                    titleRu: "Предметный тест",
                    descKy: "Химия, Биология, Тарых ж.б.",
                    descRu: "Химия, Биология, История и др.",
                  },
                  {
                    id: "practice_bank",
                    titleKy: "Машыгуу базасы",
                    titleRu: "База практики",
                    descKy: "Ылдам машыгуу жана эркин көнүгүү",
                    descRu: "Для экспресс-тренировок",
                  },
                ].map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setNewExamType(item.id as any)}
                    className={`p-3 rounded-xl border text-left transition ${
                      newExamType === item.id
                        ? "border-indigo-600 bg-white ring-2 ring-indigo-500/20 shadow-xs"
                        : "border-slate-200 bg-white/70 hover:border-slate-300"
                    }`}
                  >
                    <div className="font-bold text-xs text-slate-900">
                      {lang === "ky" ? item.titleKy : item.titleRu}
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      {lang === "ky" ? item.descKy : item.descRu}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* STEP 3: CSV File Dropzone & Validation */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-7 shadow-xs space-y-5">
        <div>
          <span className="text-xs font-bold text-indigo-600 uppercase tracking-wider block">
            {lang === "ky" ? "3-Кадам: CSV Файлын жүктөө" : "Шаг 3: Загрузка файла CSV"}
          </span>
          <h3 className="text-base font-bold text-slate-900 mt-0.5">
            {lang === "ky" ? "Монолингвалдык CSV файлы" : "Монолингвальный файл вопросов"}
          </h3>
        </div>

        {/* CSV Format Pills / Columns */}
        <div className="p-3.5 bg-slate-50 rounded-2xl border border-slate-200">
          <div className="text-xs font-bold text-slate-700 mb-1.5">
            {lang === "ky" ? "Керектүү тилкелер (Колонки):" : "Обязательные и опциональные колонки:"}
          </div>
          <div className="flex flex-wrap gap-1.5 font-mono text-[11px]">
            {[
              "section",
              "topic",
              "difficulty",
              "stem",
              "option_a",
              "option_b",
              "option_c",
              "option_d",
              "correct_option",
            ].map((col) => (
              <span
                key={col}
                className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200 font-bold"
              >
                {col}
              </span>
            ))}
            {["passage_text", "image_url", "explanation"].map((col) => (
              <span
                key={col}
                className="px-2 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200 font-medium"
              >
                {col} (опционал)
              </span>
            ))}
          </div>
        </div>

        {/* Dropzone */}
        <div className="border-2 border-dashed border-slate-300 hover:border-indigo-500 rounded-2xl p-7 text-center bg-slate-50/50 hover:bg-indigo-50/20 transition-all flex flex-col items-center justify-center">
          <UploadCloud className="w-10 h-10 text-indigo-500 mb-2" />
          <p className="text-sm font-semibold text-slate-800">
            {file ? file.name : lang === "ky" ? "CSV файлын тандаңыз же сүйрөп келиңиз" : "Перетащите CSV файл или выберите на диске"}
          </p>
          <p className="text-xs text-slate-400 mt-0.5">UTF-8 (.csv)</p>

          <label className="mt-3 inline-flex items-center px-4 py-2 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 cursor-pointer transition">
            <span>{lang === "ky" ? "Файлды тандоо" : "Обзор файла"}</span>
            <input
              type="file"
              accept=".csv"
              onChange={handleFileChange}
              className="hidden"
            />
          </label>
        </div>

        {file && !report && (
          <button
            onClick={handleValidate}
            disabled={isValidating}
            className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold shadow-sm transition flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {isValidating ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>{lang === "ky" ? "Текшерилүүдө (Dry-Run)..." : "Проверка (Dry-Run)..."}</span>
              </>
            ) : (
              <span>{lang === "ky" ? "Алдын ала текшерүү (Dry-Run)" : "Проверить файл (Dry-Run)"}</span>
            )}
          </button>
        )}
      </div>

      {/* STEP 4: Dry-Run Report & Preview */}
      {report && (
        <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-7 shadow-xs space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-bold text-indigo-600 uppercase tracking-wider block">
                {lang === "ky" ? "4-Кадам: Текшерүү жыйынтыгы" : "Шаг 4: Результаты валидации"}
              </span>
              <h3 className="text-base font-bold text-slate-900 mt-0.5">
                {report.errors.length === 0
                  ? lang === "ky"
                    ? "Бардык суроолор жарактуу!"
                    : "Все вопросы успешно проверены!"
                  : lang === "ky"
                  ? "Каталар табылды"
                  : "Обнаружены ошибки"}
              </h3>
            </div>

            <div className="flex gap-2">
              <span className="px-3 py-1 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full text-xs font-bold">
                ✓ {report.validRowsCount} {lang === "ky" ? "туура" : "валидно"}
              </span>
              {report.invalidRowsCount > 0 && (
                <span className="px-3 py-1 bg-rose-50 text-rose-700 border border-rose-200 rounded-full text-xs font-bold">
                  ✗ {report.invalidRowsCount} {lang === "ky" ? "ката" : "ошибок"}
                </span>
              )}
            </div>
          </div>

          {/* Errors list if any */}
          {report.errors.length > 0 && (
            <div className="p-4 bg-rose-50 rounded-2xl border border-rose-200 space-y-2 max-h-48 overflow-y-auto text-xs">
              {report.errors.map((e, idx) => (
                <div key={idx} className="flex items-start gap-2 text-rose-800">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <span>
                    <strong>
                      {lang === "ky" ? "Катар" : "Строка"} {e.rowNumber} [{e.field}]:
                    </strong>{" "}
                    {e.errorMessage}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Preview rows */}
          <div>
            <h4 className="text-xs font-bold text-slate-700 mb-2 uppercase tracking-wider">
              {lang === "ky" ? "Алдын ала көрүү (Preview):" : "Предпросмотр вопросов:"}
            </h4>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {report.preview.map((p, idx) => (
                <div
                  key={idx}
                  className="p-3 bg-slate-50 rounded-xl border border-slate-200 flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-2 max-w-lg truncate">
                    <span className="px-2 py-0.5 rounded bg-slate-200 text-slate-800 font-bold uppercase text-[10px]">
                      {p.section}
                    </span>
                    <span className="text-slate-800 truncate">{p.stem}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {p.passage_text && (
                      <span className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 text-[10px] font-semibold border border-blue-200">
                        Passage
                      </span>
                    )}
                    {p.image_url && (
                      <span className="px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 text-[10px] font-semibold border border-purple-200">
                        Image
                      </span>
                    )}
                    <span className="font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded">
                      Жооп: {p.correct_option}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Commit button */}
          {!uploadComplete ? (
            <button
              onClick={handleCommitBatch}
              disabled={isUploading || report.validRowsCount === 0}
              className="w-full py-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-semibold shadow-sm transition flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {isUploading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>
                    {lang === "ky"
                      ? "Базага жүктөлүүдө (450 партия менен)..."
                      : "Загрузка в базу (пакетами по 450)..."}
                  </span>
                </>
              ) : (
                <span>
                  {lang === "ky"
                    ? `${report.validRowsCount} суроону экзаменге бекитип сактоо`
                    : `Зафиксировать ${report.validRowsCount} вопросов в экзаменационный сет`}
                </span>
              )}
            </button>
          ) : (
            <div className="p-6 bg-emerald-50 rounded-2xl border border-emerald-200 text-center space-y-3">
              <CheckCircle2 className="w-10 h-10 text-emerald-600 mx-auto" />
              <h4 className="font-bold text-slate-900 text-base">
                {lang === "ky"
                  ? "Суроолор ийгиликтүү базага жүктөлдү!"
                  : "Вопросы успешно сохранены в экзаменационный сет!"}
              </h4>
              <p className="text-xs text-slate-600 max-w-md mx-auto">
                {lang === "ky"
                  ? "Бардык суроолор тандалган Экзамен топтомуна бекитилди жана даяр."
                  : "Все загруженные вопросы жестко привязаны к экзаменационному сету."}
              </p>
              <div className="pt-2 flex items-center justify-center gap-3">
                {createdExamSetId && (
                  <Link
                    href={`/${lang}/exams/${createdExamSetId}`}
                    className="px-4 py-2 bg-emerald-600 text-white rounded-xl text-xs font-semibold hover:bg-emerald-700 transition"
                  >
                    {lang === "ky" ? "Бул экзаменди көрүү" : "Открыть этот экзамен"}
                  </Link>
                )}
                <Link
                  href={`/${lang}/exams`}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition"
                >
                  {lang === "ky" ? "Экзамендер тизмеси" : "Список экзаменов"}
                </Link>
                <Link
                  href={`/${lang}/questions`}
                  className="px-4 py-2 bg-white text-slate-700 border border-slate-200 rounded-xl text-xs font-semibold hover:bg-slate-50 transition"
                >
                  {lang === "ky" ? "Суроолор базасы" : "Банк вопросов"}
                </Link>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function BulkUploadPage() {
  return (
    <Suspense
      fallback={
        <div className="p-12 text-center text-slate-400">
          <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
          <span>Жүктөлүүдө...</span>
        </div>
      }
    >
      <BulkUploadContent />
    </Suspense>
  );
}
