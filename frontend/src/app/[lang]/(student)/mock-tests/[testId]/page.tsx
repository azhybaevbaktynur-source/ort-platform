"use client";

import React, { useState, useEffect, useMemo, useCallback, useRef, Suspense } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { ExamTimer } from "@/components/exam/ExamTimer";
import { QuestionCard } from "@/components/exam/QuestionCard";
import { MathRenderer } from "@/components/math/MathRenderer";
import { NumberedPassage } from "@/components/exam/NumberedPassage";
import {
  ArrowLeft,
  ArrowRight,
  Send,
  AlertTriangle,
  AlertCircle,
  KeyRound,
  CheckCircle2,
  Layers,
  Clock,
  FileText,
  Image as ImageIcon,
  Sparkles,
  RefreshCw,
  Award,
  Lock,
  Save,
  Bookmark,
  EyeOff,
  Scale,
  ChevronUp,
  MapPin,
  X,
} from "lucide-react";
import { getAuthHeader } from "@/lib/api";
import { toast } from "@/components/ui/Toast";

interface QuestionItem {
  id: string;
  section: string;
  topic: string;
  stem: string;
  column_a?: string | null;
  column_b?: string | null;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  option_e?: string | null;
  passage_text?: string | null;
  image_url?: string | null;
}

interface SectionItem {
  section: string;
  questionCount: number;
  timeLimitMinutes: number;
}

interface SectionScore {
  section: string;
  rawScore: number;
  totalQuestions: number;
  scaledScore: number;
  accuracyPercentage: number;
}

interface MockTestFinalResult {
  attemptId: string;
  totalRawScore: number;
  maxRawScore: number;
  totalScaledScore: number;
  percentile: number;
  isGoldenCertificate: boolean;
  sectionScores: Record<string, SectionScore>;
  exam_type?: string;
  maxScaledScore?: number;
}

const STRICT_SECTION_ORDER = [
  "math_1",
  "math_2",
  "analogies",
  "reading",
  "grammar",
  "chemistry",
  "biology",
  "physics",
  "advanced_math",
  "history",
  "english",
  "native_language",
];

const DEFAULT_SECTIONS: SectionItem[] = [
  { section: "math_1", questionCount: 30, timeLimitMinutes: 45 },
  { section: "math_2", questionCount: 30, timeLimitMinutes: 45 },
  { section: "analogies", questionCount: 30, timeLimitMinutes: 30 },
  { section: "reading", questionCount: 30, timeLimitMinutes: 60 },
  { section: "grammar", questionCount: 30, timeLimitMinutes: 35 },
];

function ExamRunnerContent() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { lang, t } = useTranslation();
  const { userProfile, user } = useAuth();
  const studentName = userProfile?.displayName || user?.displayName || (lang === "ky" ? "Студент" : "Студент");

  // Popover question grid open state
  const [isGridOpen, setIsGridOpen] = useState(false);

  // Close grid popover on Escape key
  useEffect(() => {
    if (!isGridOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsGridOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isGridOpen]);

  const testId = (params?.testId as string) || "ort_main_standard";
  const pinParam = searchParams.get("pin");

  // Session state
  const [attemptId, setAttemptId] = useState<string>("");
  const [sections, setSections] = useState<SectionItem[]>(DEFAULT_SECTIONS);
  const [questionsBySection, setQuestionsBySection] = useState<Record<string, QuestionItem[]>>({});
  const [loadingSession, setLoadingSession] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [maxAttemptsExceeded, setMaxAttemptsExceeded] = useState<{ isExceeded: boolean; message: string } | null>(null);
  const [accessDenied, setAccessDenied] = useState<{ isDenied: boolean; message: string } | null>(null);

  // Exam metadata state
  const [examType, setExamType] = useState<string>("full_main");
  const [examTitle, setExamTitle] = useState<string>("");
  const [examTimeLimitMinutes, setExamTimeLimitMinutes] = useState<number | null>(null);
  const [totalTimeSeconds, setTotalTimeSeconds] = useState<number>(215 * 60);

  const isSubjectTest = useMemo(() => {
    return examType === "subject" || testId.toLowerCase().includes("subject");
  }, [examType, testId]);

  // PIN Access Code state
  const [requiresPin, setRequiresPin] = useState(false);
  const [enteredPin, setEnteredPin] = useState(pinParam || "");
  const [pinError, setPinError] = useState<string | null>(null);
  const [isVerifyingPin, setIsVerifyingPin] = useState(false);

  // Active section & question state
  const [currentSectionIndex, setCurrentSectionIndex] = useState(0);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<
    Record<string, { selectedOptionId?: string; flagged?: boolean; timeSpentSeconds?: number }>
  >({});

  // Static Manual Section Transition Interstitial State
  const [isTransitioning, setIsTransitioning] = useState(false);

  // Final submission & score state
  const [isSubmittingFinal, setIsSubmittingFinal] = useState(false);
  const [finalResult, setFinalResult] = useState<MockTestFinalResult | null>(null);

  // Timer Expiration & Auto-submit modal state
  const [isTimeExpiredModalOpen, setIsTimeExpiredModalOpen] = useState(false);

  // Save and Exit & Debounced auto-save state
  const [isSavingAndExiting, setIsSavingAndExiting] = useState(false);
  const remainingSecondsRef = useRef<number>(215 * 60);
  const [customRemainingSeconds, setCustomRemainingSeconds] = useState<number | null>(null);
  const debounceSaveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Visual elimination/strike-through of options
  const [eliminatedOptions, setEliminatedOptions] = useState<Record<string, Record<string, boolean>>>({});
  const toggleEliminate = (questionId: string, optId: string) => {
    setEliminatedOptions((prev) => ({
      ...prev,
      [questionId]: {
        ...(prev[questionId] || {}),
        [optId]: !prev[questionId]?.[optId],
      },
    }));
  };

  // Section names dictionary
  const getSectionName = (secCode: string) => {
    switch (secCode) {
      case "math_1":
        return lang === "ky" ? "1-Бөлүм: Математика I" : "Раздел 1: Математика I";
      case "math_2":
        return lang === "ky" ? "2-Бөлүм: Математика II" : "Раздел 2: Математика II";
      case "analogies":
        return lang === "ky" ? "3-Бөлүм: Аналогиялар жана сүйлөмдү толуктоо" : "Раздел 3: Аналогии и дополнение предложений";
      case "reading":
        return lang === "ky" ? "4-Бөлүм: Окуу жана түшүнүү" : "Раздел 4: Чтение и понимание текста";
      case "grammar":
        return lang === "ky" ? "5-Бөлүм: Практикалык грамматика" : "Раздел 5: Практическая грамматика";
      case "chemistry":
        return lang === "ky" ? "Химия" : "Химия";
      case "biology":
        return lang === "ky" ? "Биология" : "Биология";
      case "physics":
        return lang === "ky" ? "Физика" : "Физика";
      case "advanced_math":
        return lang === "ky" ? "Профилдик математика" : "Профильная математика";
      case "history":
        return lang === "ky" ? "Тарых" : "История";
      case "english":
        return lang === "ky" ? "Англис тили" : "Английский язык";
      case "native_language":
        return lang === "ky" ? "Кыргыз тили жана адабияты" : "Русский язык и литература";
      default:
        return secCode;
    }
  };

  // Initialize test session with backend
  const initSession = useCallback(
    async (customPin?: string) => {
      const activePin =
        customPin !== undefined ? customPin : (pinParam || undefined);
      const isForceNew =
        searchParams.get("force_new") === "true" || searchParams.get("retake") === "true";

      try {
        setLoadingSession(true);
        setSessionError(null);
        setAccessDenied(null);

        if (isForceNew) {
          try {
            localStorage.removeItem(`ort_active_attempt_${testId}`);
          } catch {}
        }

        const authHeader = await getAuthHeader();
        const res = await fetch("/api/v1/mock-tests/start", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...authHeader,
          },
          body: JSON.stringify({
            templateId: testId,
            language: lang,
            access_code: activePin || undefined,
            pin: activePin || undefined,
            force_new: isForceNew,
          }),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          const errMsg = err.detail || "Failed to start exam session";

          const isAccessDenied =
            res.status === 403 &&
            (errMsg.includes("нет доступа") ||
             errMsg.includes("мүмкүнчүлүгүңүз жок") ||
             errMsg.toLowerCase().includes("access denied") ||
             errMsg.toLowerCase().includes("not allowed"));

          if (isAccessDenied) {
            setAccessDenied({ isDenied: true, message: errMsg });
            return;
          }

          const isPinError =
            res.status === 403 &&
            (errMsg.includes("PIN") ||
             errMsg.includes("кирүү коду") ||
             errMsg.includes("код доступа") ||
             errMsg.toLowerCase().includes("access code"));

          if (isPinError) {
            setRequiresPin(true);
            if (activePin) {
              setPinError(
                lang === "ky"
                  ? "Туура эмес 4 орундуу PIN-код!"
                  : "Неверный 4-значный PIN-код!"
              );
            } else {
              setPinError(null);
            }
            return;
          }

          const isMaxAttempts =
            res.status === 403 &&
            (errMsg.includes("максималдуу аракеттер") ||
             errMsg.includes("Лимит попыток") ||
             errMsg.includes("max_attempts") ||
             errMsg.toLowerCase().includes("maximum number of attempts"));

          if (isMaxAttempts) {
            setMaxAttemptsExceeded({ isExceeded: true, message: errMsg });
            return;
          }

          throw new Error(errMsg);
        }

        const data = await res.json();
        setRequiresPin(false);
        setPinError(null);
        setAttemptId(data.attemptId);

        // Hydrate locally cached answers or backend answers (Anti-Data Loss & Resume)
        try {
          if (isForceNew) {
            setAnswers(data.answers || {});
            setCurrentIndex(0);
            setCurrentSectionIndex(0);
          } else {
            const activeCached = localStorage.getItem(`ort_active_attempt_${testId}`);
            const attemptCached = localStorage.getItem(`ort_attempt_answers_${data.attemptId}`);
            let hydrated = false;

            if (activeCached) {
              const parsed = JSON.parse(activeCached);
              if (parsed.answers && Object.keys(parsed.answers).length > 0) {
                setAnswers(parsed.answers);
                if (typeof parsed.currentIndex === "number") {
                  setCurrentIndex(parsed.currentIndex);
                }
                if (typeof parsed.currentSectionIndex === "number") {
                  setCurrentSectionIndex(parsed.currentSectionIndex);
                }
                if (typeof parsed.remainingTimeSeconds === "number" && parsed.remainingTimeSeconds > 0) {
                  setTotalTimeSeconds(parsed.remainingTimeSeconds);
                  remainingSecondsRef.current = parsed.remainingTimeSeconds;
                  setCustomRemainingSeconds(parsed.remainingTimeSeconds);
                }
                hydrated = true;
              }
            }

            if (!hydrated) {
              if (attemptCached) {
                setAnswers(JSON.parse(attemptCached));
              } else if (data.answers && Object.keys(data.answers).length > 0) {
                setAnswers(data.answers);
              }

              if (typeof data.currentSectionIndex === "number") {
                setCurrentSectionIndex(data.currentSectionIndex);
              }
              if (typeof data.currentIndex === "number") {
                setCurrentIndex(data.currentIndex);
              }
              if (typeof data.remainingTimeSeconds === "number" && data.remainingTimeSeconds > 0) {
                setTotalTimeSeconds(data.remainingTimeSeconds);
                remainingSecondsRef.current = data.remainingTimeSeconds;
                setCustomRemainingSeconds(data.remainingTimeSeconds);
              }
            }
          }
        } catch (e) {
          console.warn("Error hydrating cached answers:", e);
        }

        // Resolve exam metadata (type, title, custom time limit)
        let fetchedExamType = data.exam_type;
        let fetchedTitle = data.title;
        let fetchedTimeLimit = data.time_limit_minutes;

        if (!fetchedExamType || !fetchedTitle) {
          try {
            const examRes = await fetch(`/api/v1/exam-sets/${testId}`, {
              headers: { ...authHeader },
            });
            if (examRes.ok) {
              const examData = await examRes.json();
              if (!fetchedExamType && examData.exam_type) fetchedExamType = examData.exam_type;
              if (!fetchedTitle && examData.title) fetchedTitle = examData.title;
              if (fetchedTimeLimit === undefined && examData.time_limit_minutes !== undefined) {
                fetchedTimeLimit = examData.time_limit_minutes;
              }
            }
          } catch (e) {
            console.warn("Could not fetch extra exam metadata:", e);
          }
        }

        const currentIsSubject =
          fetchedExamType === "subject" || testId.toLowerCase().includes("subject");

        setExamType(fetchedExamType || (currentIsSubject ? "subject" : "full_main"));
        if (fetchedTitle) setExamTitle(fetchedTitle);
        if (fetchedTimeLimit !== undefined) setExamTimeLimitMinutes(fetchedTimeLimit);
        if (data.totalTimeSeconds) setTotalTimeSeconds(data.totalTimeSeconds);

        const questionsMap = data.questions || {};

        if (currentIsSubject) {
          // Dynamic Sectioning for Subject Tests: group all questions into a single continuous section
          const allQuestions: QuestionItem[] = Object.values(questionsMap).flat() as QuestionItem[];
          const singleSectionKey = "subject";
          const subjectTimeLimit =
            fetchedTimeLimit ||
            (data.totalTimeSeconds ? Math.round(data.totalTimeSeconds / 60) : 60);

          setQuestionsBySection({ [singleSectionKey]: allQuestions });
          setSections([
            {
              section: singleSectionKey,
              questionCount: allQuestions.length,
              timeLimitMinutes: subjectTimeLimit,
            },
          ]);
          setCurrentSectionIndex(0);
          setCurrentIndex(0);
        } else {
          // Standard full_main test sectioning
          setQuestionsBySection(questionsMap);

          const rawSections: SectionItem[] =
            Array.isArray(data.sections) && data.sections.length > 0
              ? data.sections
              : DEFAULT_SECTIONS;

          // Strictly sort sections by STRICT_SECTION_ORDER
          const sortedSections = [...rawSections].sort((a, b) => {
            const idxA = STRICT_SECTION_ORDER.indexOf(a.section);
            const idxB = STRICT_SECTION_ORDER.indexOf(b.section);
            return (idxA !== -1 ? idxA : 999) - (idxB !== -1 ? idxB : 999);
          });

          // Filter out sections that have 0 questions if questions exist
          const hasAnyQuestions = Object.values(questionsMap).some(
            (arr: any) => Array.isArray(arr) && arr.length > 0
          );
          const validSections = hasAnyQuestions
            ? sortedSections.filter(
                (s) => Array.isArray(questionsMap[s.section]) && questionsMap[s.section].length > 0
              )
            : sortedSections;

          setSections(validSections.length > 0 ? validSections : DEFAULT_SECTIONS);
        }
      } catch (err: any) {
        console.error("Session start error:", err);
        setSessionError(err.message || "Failed to start exam");
      } finally {
        setLoadingSession(false);
      }
    },
    [testId, lang, pinParam, searchParams]
  );

  useEffect(() => {
    initSession();
  }, [initSession]);

  const handlePinSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!enteredPin.trim()) {
      setPinError(lang === "ky" ? "Кирүү кодун жазыңыз" : "Введите код доступа");
      return;
    }
    setIsVerifyingPin(true);
    await initSession(enteredPin.trim());
    setIsVerifyingPin(false);
  };

  const activeSection = sections[currentSectionIndex] || sections[0];
  const activeQuestions = useMemo(() => {
    return questionsBySection[activeSection?.section] || [];
  }, [questionsBySection, activeSection]);

  const currentQuestion = activeQuestions[currentIndex] || activeQuestions[0];
  const questionIds = useMemo(() => activeQuestions.map((q) => q.id), [activeQuestions]);

  const isFinalSection = isSubjectTest || currentSectionIndex >= sections.length - 1;
  const nextSection = !isFinalSection ? sections[currentSectionIndex + 1] : null;

  // Overall question count & progress calculations
  const totalQuestionsCount = useMemo(() => {
    let count = 0;
    for (const key in questionsBySection) {
      count += questionsBySection[key]?.length || 0;
    }
    return count;
  }, [questionsBySection]);

  const answeredCount = useMemo(() => {
    return Object.values(answers).filter((a) => Boolean(a?.selectedOptionId)).length;
  }, [answers]);

  const progressPercentage = useMemo(() => {
    if (!totalQuestionsCount) return 0;
    return Math.min(100, Math.round((answeredCount / totalQuestionsCount) * 100));
  }, [answeredCount, totalQuestionsCount]);

  // Immediate localStorage persistence on answer or index change (Anti-Data Loss)
  useEffect(() => {
    if (!attemptId || finalResult) return;
    try {
      const activeState = {
        attemptId,
        testId,
        answers,
        currentSectionIndex,
        currentIndex,
        timestamp: Date.now(),
      };
      localStorage.setItem(`ort_active_attempt_${testId}`, JSON.stringify(activeState));
      localStorage.setItem(`ort_attempt_answers_${attemptId}`, JSON.stringify(answers));
    } catch (e) {
      console.warn("Failed to persist exam state to localStorage:", e);
    }
  }, [attemptId, testId, answers, currentSectionIndex, currentIndex, finalResult]);

  // BeforeUnload navigation guard while exam is active
  useEffect(() => {
    if (!attemptId || finalResult) return;

    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
      return "";
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [attemptId, finalResult]);

  // Bluebook conditional layout check: ONLY split into 2 columns if passage, image, or comparison
  const isSplitScreen = Boolean(
    currentQuestion && (
      Boolean(currentQuestion.passage_text) ||
      Boolean(currentQuestion.image_url) ||
      Boolean(currentQuestion.column_a || currentQuestion.column_b)
    )
  );

  // Extract clean stem text
  const stemText = useMemo(() => {
    if (!currentQuestion) return "";
    const s = currentQuestion.stem;
    if (typeof s === "object" && s !== null) {
      return lang === "ky" ? (s as any).ky : (s as any).ru;
    }
    return String(s || "").trim();
  }, [currentQuestion, lang]);

  // Extract options for currentQuestion (standard or comparison)
  const currentOptions = useMemo(() => {
    if (!currentQuestion) return [];
    const q = currentQuestion;

    const defaultComparisonTexts: Record<string, { ky: string; ru: string }> = {
      A: { ky: "КОЛОНКА А чоңураак", ru: "Значение в Колонке А больше" },
      B: { ky: "КОЛОНКА Б чоңураак", ru: "Значение в Колонке Б больше" },
      C: { ky: "Эки чоңдук барабар", ru: "Величины равны" },
      D: { ky: "Маалымат жетишсиз", ru: "Недостаточно информации для определения" },
    };

    const isComparison = Boolean(q.column_a || q.column_b);

    if (isComparison) {
      if (q.option_a || q.option_b || q.option_c || q.option_d) {
        return [
          { id: "A", text: q.option_a || (lang === "ky" ? defaultComparisonTexts.A.ky : defaultComparisonTexts.A.ru) },
          { id: "B", text: q.option_b || (lang === "ky" ? defaultComparisonTexts.B.ky : defaultComparisonTexts.B.ru) },
          { id: "C", text: q.option_c || (lang === "ky" ? defaultComparisonTexts.C.ky : defaultComparisonTexts.C.ru) },
          { id: "D", text: q.option_d || (lang === "ky" ? defaultComparisonTexts.D.ky : defaultComparisonTexts.D.ru) },
          ...(q.option_e ? [{ id: "E", text: q.option_e }] : []),
        ];
      }
      return ["A", "B", "C", "D"].map((id) => ({
        id,
        text: lang === "ky" ? defaultComparisonTexts[id].ky : defaultComparisonTexts[id].ru,
      }));
    }

    return [
      { id: "A", text: q.option_a || "" },
      { id: "B", text: q.option_b || "" },
      { id: "C", text: q.option_c || "" },
      { id: "D", text: q.option_d || "" },
      ...(q.option_e ? [{ id: "E", text: q.option_e }] : []),
    ].filter((o) => Boolean(o.text));
  }, [currentQuestion, lang]);

  // Batch sync answers & progress to backend
  const batchSyncAnswers = async () => {
    if (!attemptId || finalResult) return;
    try {
      const authHeader = await getAuthHeader();
      await fetch(`/api/v1/mock-tests/${attemptId}/save`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeader,
        },
        body: JSON.stringify({
          answers,
          currentSectionIndex,
          remainingTimeSeconds: remainingSecondsRef.current || totalTimeSeconds,
          isFinal: false,
          is_final: false,
        }),
      });
    } catch (e) {
      console.warn("Batch sync failed:", e);
    }
  };

  // Debounced auto-save to backend whenever answers change
  useEffect(() => {
    if (!attemptId || finalResult || Object.keys(answers).length === 0) return;

    if (debounceSaveTimeoutRef.current) {
      clearTimeout(debounceSaveTimeoutRef.current);
    }

    debounceSaveTimeoutRef.current = setTimeout(async () => {
      try {
        const authHeader = await getAuthHeader();
        await fetch(`/api/v1/mock-tests/${attemptId}/save`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...authHeader,
          },
          body: JSON.stringify({
            answers,
            currentSectionIndex,
            remainingTimeSeconds: remainingSecondsRef.current || totalTimeSeconds,
            isFinal: false,
            is_final: false,
          }),
        });
      } catch (e) {
        console.warn("Auto-save sync to backend failed:", e);
      }
    }, 1200);

    return () => {
      if (debounceSaveTimeoutRef.current) {
        clearTimeout(debounceSaveTimeoutRef.current);
      }
    };
  }, [answers, attemptId, currentSectionIndex, totalTimeSeconds, finalResult]);

  // Handle Save and Exit: saves answers + remaining time and navigates to mock-tests
  const handleSaveAndExit = async () => {
    if (!attemptId) {
      router.push(`/${lang}/mock-tests`);
      return;
    }

    setIsSavingAndExiting(true);
    try {
      const authHeader = await getAuthHeader();
      const payload = {
        answers,
        currentSectionIndex,
        remainingTimeSeconds: remainingSecondsRef.current || totalTimeSeconds,
        isFinal: false,
        is_final: false,
      };
      console.log("Saving payload:", payload);

      // Immediate local state persistence
      try {
        localStorage.setItem(
          `ort_active_attempt_${testId}`,
          JSON.stringify({
            attemptId,
            testId,
            answers,
            currentSectionIndex,
            currentIndex,
            remainingTimeSeconds: remainingSecondsRef.current,
            timestamp: Date.now(),
          })
        );
        localStorage.setItem(`ort_attempt_answers_${attemptId}`, JSON.stringify(answers));
      } catch (e) {
        console.warn("Failed to cache to localStorage on exit:", e);
      }

      await fetch(`/api/v1/mock-tests/${attemptId}/save`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeader,
        },
        body: JSON.stringify(payload),
      });

      toast.success(
        lang === "ky"
          ? "Сиздин прогрессиңиз ийгиликтүү сакталды!"
          : "Ваш прогресс успешно сохранен!"
      );
      router.refresh();
      router.push(`/${lang}/mock-tests`);
    } catch (err) {
      console.error("Save & Exit error:", err);
      toast.error(
        lang === "ky"
          ? "Сактоодо ката кетти. Кайра аракет кылыңыз."
          : "Ошибка при сохранении. Попробуйте еще раз."
      );
    } finally {
      setIsSavingAndExiting(false);
    }
  };

  const handleSelectOption = (optionId: string) => {
    if (!currentQuestion) return;
    setAnswers((prev) => {
      const updated = {
        ...prev,
        [currentQuestion.id]: {
          ...prev[currentQuestion.id],
          selectedOptionId: optionId,
          timeSpentSeconds: (prev[currentQuestion.id]?.timeSpentSeconds || 0) + 5,
        },
      };
      if (attemptId) {
        try {
          localStorage.setItem(`ort_attempt_answers_${attemptId}`, JSON.stringify(updated));
        } catch (e) {
          console.warn("Failed to cache answers to localStorage:", e);
        }
      }
      return updated;
    });
  };

  const handleToggleFlag = () => {
    if (!currentQuestion) return;
    setAnswers((prev) => {
      const updated = {
        ...prev,
        [currentQuestion.id]: {
          ...prev[currentQuestion.id],
          flagged: !prev[currentQuestion.id]?.flagged,
        },
      };
      if (attemptId) {
        try {
          localStorage.setItem(`ort_attempt_answers_${attemptId}`, JSON.stringify(updated));
        } catch (e) {
          console.warn("Failed to cache answers to localStorage:", e);
        }
      }
      return updated;
    });
  };

  // Section time expired or student clicks Finish Section
  const handleSectionTimeExpiredOrFinish = () => {
    if (isSubjectTest) {
      handleSubmitFinalTest();
    } else {
      setIsTransitioning(true);
    }
  };

  // Complete Transition: student manually clicks Continue button to enter next section or submit
  const handleCompleteTransition = async () => {
    setIsTransitioning(false);

    if (isFinalSection) {
      // Final Section completed -> submit entire exam
      await handleSubmitFinalTest();
    } else {
      // High-concurrency batch sync before switching section
      await batchSyncAnswers();
      // Move to next section
      setCustomRemainingSeconds(null);
      setCurrentSectionIndex((prev) => prev + 1);
      setCurrentIndex(0);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  // Final Exam Submission
  const handleSubmitFinalTest = async (isAutoSubmit = false) => {
    if (isSubmittingFinal) return;
    if (debounceSaveTimeoutRef.current) {
      clearTimeout(debounceSaveTimeoutRef.current);
      debounceSaveTimeoutRef.current = null;
    }
    setIsSubmittingFinal(true);
    try {
      const authHeader = await getAuthHeader();
      const payload = {
        answers,
        currentSectionIndex,
        remainingTimeSeconds: 0,
        isFinal: true,
        is_final: true,
      };
      console.log("Submitting payload:", payload);

      const res = await fetch(`/api/v1/mock-tests/${attemptId}/submit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeader,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error("Failed to submit exam");
      }

      const result = await res.json();
      // Clear localStorage cache on successful test submission
      try {
        localStorage.removeItem(`ort_active_attempt_${testId}`);
        localStorage.removeItem(`ort_attempt_answers_${attemptId}`);
        sessionStorage.setItem(`ort_result_${testId}`, JSON.stringify(result));
      } catch {}
      setFinalResult(result);
      setIsTimeExpiredModalOpen(false);
      router.refresh();
      toast.success(
        lang === "ky"
          ? "Экзамен ийгиликтүү аяктады жана бааланды!"
          : "Экзамен успешно завершен и проверен!"
      );
    } catch (err: any) {
      console.error("Submit test error:", err);
      if (isAutoSubmit) {
        try {
          await batchSyncAnswers();
        } catch {}
        setIsTimeExpiredModalOpen(false);
        toast.error(
          lang === "ky"
            ? "Убакыт бүттү. Жыйынтыктар сакталды."
            : "Время вышло. Результаты сохранены."
        );
        router.push(`/${lang}/dashboard`);
      } else {
        toast.error(err.message || (lang === "ky" ? "Жөнөтүү катасы" : "Ошибка отправки теста"));
      }
    } finally {
      setIsSubmittingFinal(false);
    }
  };

  // Dedicated Auto-submit handler triggered when timer expires (00:00)
  const handleTimeExpiredAutoSubmit = async () => {
    setIsTimeExpiredModalOpen(true);
    await handleSubmitFinalTest(true);
  };

  // PIN Access Code Required Screen
  if (requiresPin && !attemptId) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-3xl border border-slate-200/80 p-8 text-center space-y-6 shadow-xl shadow-slate-100">
          <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mx-auto shadow-xs">
            <KeyRound className="w-8 h-8" />
          </div>

          <div className="space-y-2">
            <h3 className="font-extrabold text-slate-900 text-xl tracking-tight">
              {lang === "ky" ? "Экзаменге кирүү коду" : "Код доступа к экзамену"}
            </h3>
            <p className="text-xs text-slate-500 leading-relaxed max-w-xs mx-auto">
              {lang === "ky"
                ? "Бул сыноо тестине кирүү үчүн 4 орундуу PIN-кодду жазыңыз."
                : "Для прохождения данного теста введите 4-значный PIN-код доступа."}
            </p>
          </div>

          <form onSubmit={handlePinSubmit} className="space-y-4">
            <div>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={4}
                value={enteredPin}
                onChange={(e) => {
                  const val = e.target.value.replace(/[^0-9]/g, "").slice(0, 4);
                  setEnteredPin(val);
                  if (pinError) setPinError(null);
                }}
                placeholder="0000"
                autoFocus
                className="w-48 mx-auto text-center tracking-[0.5em] text-2xl font-mono font-bold py-3 px-4 bg-slate-50 border border-slate-200 rounded-2xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition"
              />
              {pinError && (
                <div className="flex items-center justify-center gap-1.5 mt-2.5 text-xs font-semibold text-rose-600">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                  <span>{pinError}</span>
                </div>
              )}
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-2 pt-2">
              <Link
                href={`/${lang}/mock-tests`}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>{lang === "ky" ? "Артка кайтуу" : "Назад к тестам"}</span>
              </Link>

              <button
                type="submit"
                disabled={isVerifyingPin || enteredPin.length !== 4}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl text-xs font-bold transition shadow-xs cursor-pointer"
              >
                {isVerifyingPin ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="w-4 h-4" />
                )}
                <span>{lang === "ky" ? "Кирүү жана баштоо" : "Войти и начать"}</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  // Access Denied screen
  if (accessDenied?.isDenied) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-3xl border border-slate-200 p-8 text-center space-y-5 shadow-sm">
          <div className="w-14 h-14 rounded-2xl bg-rose-50 text-rose-600 flex items-center justify-center mx-auto border border-rose-200">
            <Lock className="w-7 h-7" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 text-lg">
              {lang === "ky" ? "Кирүүгө уруксат жок" : "Доступ ограничен"}
            </h3>
            <p className="text-xs text-slate-600 mt-2 leading-relaxed">
              {lang === "ky"
                ? "Бул экзаменге кирүү мүмкүнчүлүгүңүз жок. Мугалимден же администратордон уруксат сураңыз."
                : "У вас нет доступа к этому экзамену. Обратитесь к администратору для получения доступа."}
            </p>
          </div>
          <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              href={`/${lang}/dashboard`}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition shadow-xs"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>{lang === "ky" ? "Дашбордго кайтуу" : "Вернуться в дашборд"}</span>
            </Link>
            <Link
              href={`/${lang}/mock-tests`}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-slate-100 text-slate-700 rounded-xl text-xs font-semibold hover:bg-slate-200 transition"
            >
              <span>{lang === "ky" ? "Сыноо тесттерге кайтуу" : "К списку тестов"}</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Max attempts exceeded screen
  if (maxAttemptsExceeded) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-3xl border border-slate-200 p-8 text-center space-y-5 shadow-sm">
          <div className="w-14 h-14 rounded-2xl bg-amber-50 text-amber-600 flex items-center justify-center mx-auto border border-amber-200">
            <AlertCircle className="w-7 h-7" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 text-lg">
              {lang === "ky" ? "Аракеттердин чеги бүттү" : "Лимит попыток исчерпан"}
            </h3>
            <p className="text-xs text-slate-500 mt-2 leading-relaxed">
              {lang === "ky"
                ? "Сиз бул экзаменди тапшыруу үчүн берилген максималдуу аракеттер санын толук колдондуңуз. Сиздин бардык жыйынтыктарыңыз сакталган."
                : "Вы достигли максимального количества попыток для этого экзамена. Ваши результаты успешно сохранены в системе."}
            </p>
          </div>
          <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              href={`/${lang}/mock-tests`}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition shadow-xs"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>{lang === "ky" ? "Сыноо тесттерге кайтуу" : "К списку тестов"}</span>
            </Link>
            <Link
              href={`/${lang}/progress`}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-slate-100 text-slate-700 rounded-xl text-xs font-semibold hover:bg-slate-200 transition"
            >
              <span>{lang === "ky" ? "Статистиканы көрүү" : "Моя статистика"}</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Error screen
  if (sessionError) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-3xl border border-slate-200 p-8 text-center space-y-4 shadow-sm">
          <div className="w-12 h-12 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center mx-auto">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <h3 className="font-bold text-slate-900 text-lg">
            {lang === "ky" ? "Экзамен башталган жок" : "Ошибка запуска экзамена"}
          </h3>
          <p className="text-xs text-slate-500 leading-relaxed">{sessionError}</p>
          <div className="pt-2">
            <Link
              href={`/${lang}/mock-tests`}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>{lang === "ky" ? "Сыноо тесттерине кайтуу" : "Назад к списку тестов"}</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Loading screen
  if (loadingSession) {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center gap-3 text-slate-400">
        <RefreshCw className="w-8 h-8 animate-spin text-indigo-600" />
        <span className="text-sm font-medium">{t("common.loading")}</span>
      </div>
    );
  }

  // Final Results Screen
  if (finalResult) {
    return (
      <div className="max-w-4xl mx-auto py-8 space-y-6">
        <div className="bg-white rounded-3xl border border-slate-200 p-8 shadow-sm text-center space-y-4">
          <div className="w-16 h-16 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto shadow-xs">
            <Award className="w-9 h-9" />
          </div>

          <h2 className="text-2xl font-extrabold text-slate-900">
            {lang === "ky" ? "Сынак ийгиликтүү аяктады!" : "Экзамен успешно завершен!"}
          </h2>

          <p className="text-sm text-slate-500 max-w-md mx-auto">
            {isSubjectTest
              ? lang === "ky"
                ? "Тест ийгиликтүү аяктады. Сиздин жыйынтыгыңыз:"
                : "Тест завершен. Ваш итоговый результат:"
              : lang === "ky"
              ? "Бардык 5 бөлүм тапшырылды. Сиздин ОРТ нормативдик шкаласындагы упайыңыз:"
              : "Все разделы завершены. Ваш итоговый результат по нормативной шкале ОРТ:"}
          </p>

          <div className="py-4">
            <span className="text-5xl font-extrabold text-indigo-600 tracking-tight">
              {finalResult.totalScaledScore}
            </span>
            <span className="text-sm text-slate-400 block mt-1">
              {finalResult.exam_type === "subject" || isSubjectTest
                ? lang === "ky"
                  ? "балл (60 — 150)"
                  : "баллов (60 - 150)"
                : lang === "ky"
                ? "балл (110 — 245)"
                : "баллов (110 - 245)"}
            </span>
            {finalResult.isGoldenCertificate && (
              <span className="inline-block mt-2 px-3 py-1 bg-amber-100 text-amber-900 border border-amber-300 rounded-full text-xs font-bold">
                ⭐ {lang === "ky" ? "Алтын Сертификат деңгээли!" : "Уровень Золотого Сертификата!"}
              </span>
            )}
          </div>

          {/* Section Breakdown Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-left pt-4 border-t border-slate-100">
            {Object.entries(finalResult.sectionScores || {}).map(([sec, sc]) => (
              <div key={sec} className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] font-bold text-slate-400 uppercase block truncate">
                  {isSubjectTest ? (examTitle || getSectionName(sec)) : getSectionName(sec)}
                </span>
                <span className="text-lg font-bold text-slate-900 block mt-0.5">
                  {sc.scaledScore}
                </span>
                <span className="text-[11px] text-emerald-600 font-semibold block">
                  {sc.rawScore} / {sc.totalQuestions} ({sc.accuracyPercentage}%)
                </span>
              </div>
            ))}
          </div>

          <div className="pt-6 flex flex-wrap items-center justify-center gap-3">
            <Link
              href={`/${lang}/mistakes`}
              className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold shadow-sm transition"
            >
              {lang === "ky" ? "Каталарды талдоо" : "Разбор ошибок"}
            </Link>
            <button
              onClick={() => {
                router.refresh();
                router.push(`/${lang}/mock-tests`);
              }}
              className="px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition cursor-pointer"
            >
              {lang === "ky" ? "Сыноо тесттерге кайтуу" : "К списку тестов"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Question Header Component (Teacher topic slugs removed)
  const renderQuestionHeader = () => (
    <div className="flex items-center justify-between border-b border-slate-200/60 pb-3.5">
      <div className="flex items-center gap-2.5">
        <span className="px-3 py-1 rounded-lg bg-indigo-50 text-indigo-700 font-sans font-bold text-xs uppercase tracking-wide">
          {t("exam.question")} {currentIndex + 1} {t("exam.of")} {activeQuestions.length}
        </span>
      </div>

      <button
        type="button"
        onClick={handleToggleFlag}
        disabled={isTimeExpiredModalOpen}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-sans font-semibold border transition-all cursor-pointer ${
          answers[currentQuestion?.id]?.flagged
            ? "bg-amber-100 border-amber-300 text-amber-800"
            : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
        }`}
      >
        <Bookmark className={`w-3.5 h-3.5 ${answers[currentQuestion?.id]?.flagged ? "fill-amber-600 text-amber-600" : ""}`} />
        <span>{answers[currentQuestion?.id]?.flagged ? t("exam.unflag") : t("exam.flagForReview")}</span>
      </button>
    </div>
  );

  // Compact Option Buttons Component (Bluebook typography and styling)
  const renderOptions = () => (
    <div className="pt-1">
      {currentOptions.map((opt) => {
        const isSelected = answers[currentQuestion?.id]?.selectedOptionId === opt.id;
        const isEliminated = Boolean(eliminatedOptions[currentQuestion?.id]?.[opt.id]);
        const isComparison = Boolean(currentQuestion?.column_a || currentQuestion?.column_b);

        return (
          <div
            key={opt.id}
            onClick={() => {
              if (isTimeExpiredModalOpen || isSubmittingFinal) return;
              if (isEliminated) {
                toggleEliminate(currentQuestion.id, opt.id);
              }
              handleSelectOption(opt.id);
            }}
            className={`flex items-center justify-between w-full py-3 px-4 gap-3 mb-2 rounded-xl border text-left transition-all cursor-pointer ${
              isEliminated
                ? "opacity-40 line-through bg-slate-50 border-slate-200 text-slate-400"
                : isSelected
                ? "border-indigo-600 bg-indigo-50/50 ring-2 ring-indigo-500 font-medium text-slate-900 shadow-xs"
                : "border-slate-200 hover:border-indigo-300 bg-white text-slate-800 hover:bg-slate-50/50"
            }`}
          >
            <div className="flex items-center gap-3 flex-1 min-w-0 pr-2">
              <span
                className={`w-7 h-7 rounded-full flex items-center justify-center font-sans font-semibold text-sm shrink-0 transition-colors ${
                  isEliminated
                    ? "bg-slate-200 text-slate-500"
                    : isSelected
                    ? "bg-indigo-600 text-white shadow-xs"
                    : "bg-slate-100 border border-slate-200 text-slate-700"
                }`}
              >
                {opt.id}
              </span>
              <div className={`flex-1 font-serif text-gray-900 leading-relaxed text-base ${isEliminated ? "line-through text-slate-400" : ""}`}>
                <MathRenderer content={opt.text} />
              </div>
            </div>

            {isComparison && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleEliminate(currentQuestion.id, opt.id);
                }}
                className={`p-1.5 rounded-lg transition-colors cursor-pointer shrink-0 ${
                  isEliminated
                    ? "text-slate-700 bg-slate-200/80 hover:bg-slate-300"
                    : "text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                }`}
                title={
                  isEliminated
                    ? (lang === "ky" ? "Вариантты кайтаруу" : "Восстановить вариант")
                    : (lang === "ky" ? "Вариантты чийип салуу" : "Исключить вариант (зачеркнуть)")
                }
                aria-label={lang === "ky" ? "Вариантты чийип салуу" : "Исключить вариант"}
              >
                <EyeOff className={`w-3.5 h-3.5 ${isEliminated ? "stroke-[2.5]" : ""}`} />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );

  return (
    <div className="h-auto lg:h-[calc(100vh-80px)] overflow-y-auto lg:overflow-hidden flex flex-col pb-24 relative">
      {/* TIME EXPIRED NON-DISMISSIBLE MODAL */}
      {isTimeExpiredModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-md p-4 animate-in fade-in select-none">
          <div className="bg-white w-full max-w-md rounded-3xl p-8 text-center space-y-5 shadow-2xl border border-slate-100">
            <div className="w-16 h-16 rounded-2xl bg-amber-50 text-amber-600 flex items-center justify-center mx-auto border border-amber-200">
              <Clock className="w-8 h-8 animate-pulse" />
            </div>

            <div className="space-y-2">
              <h3 className="text-xl font-bold text-slate-900 font-sans">
                {lang === "ky" ? "Убакыт бүттү" : "Время вышло"}
              </h3>
              <p className="text-sm text-slate-600 font-sans leading-relaxed">
                {lang === "ky"
                  ? "Убакыт бүттү. Жыйынтыктар сакталууда..."
                  : "Время вышло. Сохранение результатов..."}
              </p>
            </div>

            <div className="flex items-center justify-center gap-2 text-indigo-600 font-medium text-xs font-sans pt-2">
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span>{lang === "ky" ? "Сураныч, күтө туруңуз..." : "Пожалуйста, подождите..."}</span>
            </div>
          </div>
        </div>
      )}

      {/* STATIC MANUAL SECTION TRANSITION INTERSTITIAL MODAL (Hidden for Subject Tests) */}
      {!isSubjectTest && isTransitioning && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-md p-4 animate-in fade-in">
          <div className="bg-white w-full max-w-md rounded-3xl p-8 text-center space-y-6 shadow-2xl border border-slate-100">
            <div className="w-16 h-16 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-8 h-8" />
            </div>

            <div>
              <h3 className="text-lg font-bold text-slate-900">
                {lang === "ky"
                  ? "Бөлүм аяктады. Сиздин жоопторуңуз сакталды"
                  : "Раздел завершен. Ваши ответы сохранены"}
              </h3>
            </div>

            {/* Next Section Details */}
            {!isFinalSection && nextSection ? (
              <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-4 text-left space-y-3">
                <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                  {lang === "ky" ? "Кийинки бөлүм" : "Следующий раздел"}
                </div>
                <div className="text-base font-bold text-slate-900">
                  {getSectionName(nextSection.section)}
                </div>
                <div className="flex items-center gap-4 text-xs text-slate-600">
                  <div className="flex items-center gap-1.5 font-medium">
                    <FileText className="w-4 h-4 text-indigo-500" />
                    <span>{nextSection.questionCount || 30} {lang === "ky" ? "суроо" : "вопросов"}</span>
                  </div>
                  <div className="flex items-center gap-1.5 font-medium">
                    <Clock className="w-4 h-4 text-indigo-500" />
                    <span>
                      {nextSection.timeLimitMinutes > 0
                        ? `${nextSection.timeLimitMinutes} ${lang === "ky" ? "мүнөт" : "минут"}`
                        : (lang === "ky" ? "Чектөөсүз" : "Без лимита")}
                    </span>
                  </div>
                </div>
                <p className="text-[11px] text-slate-500 pt-2 border-t border-slate-200/60 leading-relaxed">
                  {lang === "ky"
                    ? "Даяр болгондо 'Кийинки бөлүмгө өтүү' баскычын басыңыз. Убакыт басылгандан кийин гана эсептеле баштайт."
                    : "Нажмите 'Продолжить', когда будете готовы. Таймер нового раздела начнется только после нажатия."}
                </p>
              </div>
            ) : (
              <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4 text-emerald-800 text-xs text-left leading-relaxed">
                {lang === "ky"
                  ? "Бардык бөлүмдөр аяктады! Тестти толугу менен тапшырып, расмий баллдарды көрүү үчүн төмөнкү баскычты басыңыз."
                  : "Все разделы экзамена завершены! Нажмите кнопку ниже, чтобы отправить результаты и просмотреть итоговую шкалу баллов."}
              </div>
            )}

            <div>
              {!isFinalSection ? (
                <button
                  onClick={handleCompleteTransition}
                  className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold shadow-md hover:shadow-lg transition flex items-center justify-center gap-2"
                >
                  <span>{lang === "ky" ? "Кийинки бөлүмгө өтүү" : "Продолжить"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              ) : (
                <button
                  onClick={handleCompleteTransition}
                  disabled={isSubmittingFinal}
                  className="w-full py-3.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-bold shadow-md hover:shadow-lg transition flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {isSubmittingFinal && <RefreshCw className="w-4 h-4 animate-spin" />}
                  <span>
                    {lang === "ky"
                      ? "Тестти аяктоо жана жыйынтыкты көрүү"
                      : "Завершить тест и посмотреть результаты"}
                  </span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TOP CBT EXAM BAR */}
      <div className="shrink-0 bg-white/95 backdrop-blur-md rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden mb-4">
        <div className="px-5 py-3 flex items-center justify-between gap-4">
          {/* Section title & progress */}
          <div className="flex items-center gap-3">
            <span className="p-2 rounded-xl bg-indigo-50 text-indigo-600">
              <Layers className="w-4 h-4" />
            </span>
            <div>
              <span className="text-xs font-bold text-slate-900 block">
                {isSubjectTest
                  ? (examTitle || (lang === "ky" ? "Предметтик тест" : "Предметный тест"))
                  : getSectionName(activeSection.section)}
              </span>
              <span className="text-[11px] text-slate-400">
                {isSubjectTest
                  ? `${answeredCount} / ${activeQuestions.length} ${lang === "ky" ? "жооп берилди" : "отвечено"}`
                  : `${currentSectionIndex + 1} / ${sections.length} ${lang === "ky" ? "бөлүм" : "раздел"} • ${answeredCount} / ${totalQuestionsCount} ${lang === "ky" ? "жооп берилди" : "отвечено"}`}
              </span>
            </div>
          </div>

          {/* Timer & Action buttons */}
          <div className="flex items-center gap-2 sm:gap-3">
            {/* "Сохранить и выйти" (Save and Exit) Button */}
            <button
              type="button"
              onClick={handleSaveAndExit}
              disabled={isSavingAndExiting}
              className="inline-flex items-center gap-1.5 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition cursor-pointer disabled:opacity-50"
              title={lang === "ky" ? "Сактоо жана чыгуу" : "Сохранить и выйти"}
            >
              {isSavingAndExiting ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-600" />
              ) : (
                <Save className="w-3.5 h-3.5 text-slate-600" />
              )}
              <span className="hidden sm:inline">
                {lang === "ky" ? "Сактоо жана чыгуу" : "Сохранить и выйти"}
              </span>
            </button>

            <ExamTimer
              key={
                isSubjectTest
                  ? `timer_global_${attemptId}`
                  : `timer_${activeSection?.section}_${customRemainingSeconds ?? "default"}`
              }
              initialSeconds={
                customRemainingSeconds !== null
                  ? customRemainingSeconds
                  : isSubjectTest
                  ? (examTimeLimitMinutes ? examTimeLimitMinutes * 60 : (totalTimeSeconds || 60 * 60))
                  : (activeSection?.timeLimitMinutes > 0 ? activeSection.timeLimitMinutes * 60 : null)
              }
              onTimeExpired={handleTimeExpiredAutoSubmit}
              onTick={(sec) => {
                remainingSecondsRef.current = sec;
              }}
            />

            <button
              onClick={() => {
                if (isSubjectTest || isFinalSection) {
                  handleSubmitFinalTest(false);
                } else {
                  handleSectionTimeExpiredOrFinish();
                }
              }}
              disabled={isSubmittingFinal || isTimeExpiredModalOpen}
              className="hidden sm:flex items-center gap-1.5 px-3.5 py-2 bg-slate-100 hover:bg-rose-50 hover:text-rose-700 text-slate-700 rounded-xl text-xs font-semibold transition cursor-pointer disabled:opacity-50"
            >
              {isSubmittingFinal ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              )}
              <span>
                {isSubjectTest || isFinalSection
                  ? lang === "ky"
                    ? "Экзаменди аяктоо"
                    : "Завершить тест"
                  : lang === "ky"
                  ? "Бөлүмдү тапшыруу"
                  : "Завершить раздел"}
              </span>
            </button>
          </div>
        </div>

        {/* Thin progress bar */}
        <div className="w-full bg-slate-100 h-1 overflow-hidden">
          <div
            className="h-1 bg-indigo-600 transition-all duration-300 ease-out"
            style={{ width: `${progressPercentage}%` }}
          />
        </div>
      </div>

      {/* CONDITIONAL LAYOUT: Single-Column (Default) vs Two-Column (Split-Screen) */}
      {!isSplitScreen ? (
        /* SINGLE-COLUMN LAYOUT: Centered for standard multiple-choice questions */
        <div className="flex-1 min-h-0 max-w-3xl mx-auto w-full flex flex-col justify-between lg:overflow-hidden pb-1">
          <div className="h-full overflow-y-auto bg-white rounded-2xl shadow-sm border border-gray-200 p-6 md:p-8 flex flex-col justify-between space-y-6">
            {currentQuestion ? (
              <div className="space-y-5">
                {renderQuestionHeader()}

                {/* Question Stem directly rendered (no Context header block) */}
                <div className="font-serif text-gray-900 leading-relaxed text-base md:text-lg">
                  <MathRenderer content={stemText} />
                </div>

                {/* Options placed directly below the stem */}
                {renderOptions()}
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-400 text-sm">
                {lang === "ky" ? "Суроолор жүктөлүүдө..." : "Загрузка вопросов..."}
              </div>
            )}
          </div>
        </div>
      ) : (
        /* TWO-COLUMN GRID: ONLY when passage_text, image_url, or comparison (column_a/b) exist */
        <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-2 gap-6 lg:overflow-hidden pb-1">
          {/* Left Pane (Context/Reading/Comparison/Image) */}
          <div className="h-full overflow-y-auto bg-white rounded-2xl shadow-sm border border-gray-200 p-6 space-y-4">
            {currentQuestion ? (
              <>
                {currentQuestion.passage_text ? (
                  /* READING PASSAGE WITH 5-LINE NUMBERING */
                  <div className="space-y-4">
                    <div className="text-[11px] font-sans font-bold text-indigo-700 uppercase tracking-wider flex items-center gap-1.5 border-b border-slate-100 pb-3">
                      <FileText className="w-4 h-4" />
                      <span>{lang === "ky" ? "Окуу тексти (Материал)" : "Материал для чтения (Текст)"}</span>
                    </div>

                    {currentQuestion.image_url && (
                      <div className="bg-slate-50 rounded-xl border border-slate-200 p-3">
                        <div className="text-[11px] font-sans font-bold text-purple-700 uppercase tracking-wider mb-2 flex items-center gap-1">
                          <ImageIcon className="w-3.5 h-3.5" />
                          <span>{lang === "ky" ? "Диаграмма / Иллюстрация" : "Диаграмма / Иллюстрация"}</span>
                        </div>
                        <img
                          src={currentQuestion.image_url}
                          alt="Reading illustration"
                          className="max-w-full max-h-60 mx-auto object-contain rounded-lg"
                        />
                      </div>
                    )}

                    <NumberedPassage text={currentQuestion.passage_text} />
                  </div>
                ) : (currentQuestion.column_a || currentQuestion.column_b) ? (
                  /* QUANTITATIVE COMPARISONS GIVEN CONDITIONS & COLUMNS */
                  <div className="space-y-4">
                    {/* Stem text if condition is given (without redundant context headers) */}
                    {stemText && (
                      <div className="font-serif text-gray-900 leading-relaxed text-base">
                        <MathRenderer content={stemText} />
                      </div>
                    )}

                    {currentQuestion.image_url && (
                      <div className="bg-slate-50 rounded-xl border border-slate-200 p-3">
                        <img
                          src={currentQuestion.image_url}
                          alt="Comparison figure"
                          className="max-w-full max-h-60 mx-auto object-contain rounded-lg"
                        />
                      </div>
                    )}

                    {/* Side-by-side comparison boxes */}
                    <div className="grid grid-cols-2 gap-4 pt-2">
                      {/* Column A */}
                      <div className="bg-slate-50/60 rounded-2xl border-2 border-slate-200 p-4 md:p-6 flex flex-col justify-between text-center shadow-xs">
                        <div className="inline-block bg-gray-100 text-gray-500 font-bold text-xs tracking-widest uppercase px-3 py-1 rounded-md mx-auto mb-3">
                          {lang === "ky" ? "КОЛОНКА А" : "КОЛОНКА А"}
                        </div>
                        <div className="py-2 flex items-center justify-center min-h-[60px] text-xl font-semibold text-gray-900">
                          <MathRenderer content={currentQuestion.column_a || "—"} />
                        </div>
                      </div>

                      {/* Column B */}
                      <div className="bg-slate-50/60 rounded-2xl border-2 border-slate-200 p-4 md:p-6 flex flex-col justify-between text-center shadow-xs">
                        <div className="inline-block bg-gray-100 text-gray-500 font-bold text-xs tracking-widest uppercase px-3 py-1 rounded-md mx-auto mb-3">
                          {lang === "ky" ? "КОЛОНКА Б" : "КОЛОНКА Б"}
                        </div>
                        <div className="py-2 flex items-center justify-center min-h-[60px] text-xl font-semibold text-gray-900">
                          <MathRenderer content={currentQuestion.column_b || "—"} />
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  /* STANDARD QUESTION WITH IMAGE */
                  <div className="space-y-4">
                    {currentQuestion.image_url && (
                      <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-xs">
                        <img
                          src={currentQuestion.image_url}
                          alt="Problem figure"
                          className="max-w-full max-h-72 mx-auto object-contain rounded-lg"
                        />
                      </div>
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-400 text-sm">
                {lang === "ky" ? "Суроолор жүктөлүүдө..." : "Загрузка вопросов..."}
              </div>
            )}
          </div>

          {/* Right Pane (Questions & Options) */}
          <div className="h-full overflow-y-auto bg-gray-50/50 rounded-2xl p-6 flex flex-col justify-between space-y-6">
            {currentQuestion ? (
              <div className="space-y-5">
                {renderQuestionHeader()}

                {/* Question Stem / Prompt */}
                <div className="font-serif text-gray-900 text-base leading-relaxed">
                  {currentQuestion.passage_text ? (
                    <MathRenderer content={stemText} />
                  ) : (currentQuestion.column_a || currentQuestion.column_b) ? (
                    <span>{lang === "ky" ? "Чоңдуктарды салыштырып, туура вариантты тандаңыз:" : "Сравните величины и выберите верное утверждение:"}</span>
                  ) : (
                    <MathRenderer content={stemText} />
                  )}
                </div>

                {/* Compact Multiple Choice Options */}
                {renderOptions()}
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-400 text-sm">
                {lang === "ky" ? "Суроолор жүктөлүүдө..." : "Загрузка вопросов..."}
              </div>
            )}
          </div>
        </div>
      )}

      {/* FIXED BOTTOM BAR (CollegeBoard Bluebook Style) */}
      <footer className="fixed bottom-0 left-0 right-0 h-16 bg-[#f4f4f4] border-t border-gray-300 flex items-center justify-between px-6 z-50 select-none">
        {/* Left Section: Student's name */}
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-sans font-medium text-gray-800 text-sm truncate max-w-[160px] sm:max-w-xs">
            {studentName}
          </span>
        </div>

        {/* Center Section: Popover Trigger & Anchored Popover Box */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setIsGridOpen((prev) => !prev)}
            className="bg-gray-800 text-white px-4 py-2 rounded-md font-sans text-sm font-medium flex items-center gap-2 hover:bg-gray-700 transition-colors cursor-pointer shadow-xs"
          >
            <span>
              {lang === "ky"
                ? `Суроо ${currentIndex + 1} / ${activeQuestions.length}`
                : lang === "ru"
                ? `Вопрос ${currentIndex + 1} из ${activeQuestions.length}`
                : `Question ${currentIndex + 1} of ${activeQuestions.length}`}
            </span>
            <ChevronUp className={`w-4 h-4 transition-transform duration-200 ${isGridOpen ? "rotate-180" : ""}`} />
          </button>

          {/* Popover Question Grid */}
          {isGridOpen && (
            <>
              {/* Click-away backdrop */}
              <div
                className="fixed inset-0 z-40 bg-transparent cursor-default"
                onClick={() => setIsGridOpen(false)}
              />

              {/* Popover Box anchored just above the center button */}
              <div className="absolute bottom-20 left-1/2 -translate-x-1/2 bg-white rounded-2xl shadow-2xl border border-gray-200 w-[400px] max-w-[calc(100vw-32px)] p-0 overflow-hidden z-50 flex flex-col animate-in fade-in zoom-in-95 duration-150">
                {/* Popover Header */}
                <div className="flex items-center justify-between p-4 border-b border-gray-100 bg-white">
                  <h4 className="font-sans font-bold text-gray-900 text-sm sm:text-base truncate">
                    {isSubjectTest
                      ? (examTitle || (lang === "ky" ? "Предметтик тест" : "Предметный тест"))
                      : getSectionName(activeSection.section)}
                  </h4>
                  <button
                    type="button"
                    onClick={() => setIsGridOpen(false)}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors cursor-pointer"
                    aria-label="Close"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* Legend */}
                <div className="flex items-center justify-around px-4 py-2.5 bg-gray-50/90 border-b border-gray-100 text-xs font-sans text-gray-600">
                  <div className="flex items-center gap-1.5">
                    <MapPin className="w-3.5 h-3.5 text-black fill-black shrink-0" />
                    <span>{lang === "ky" ? "Учурдагы" : lang === "ru" ? "Текущий" : "Current"}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-3.5 h-3.5 border-2 border-dashed border-gray-400 rounded-xs shrink-0 inline-block" />
                    <span>{lang === "ky" ? "Жоопсуз" : lang === "ru" ? "Не отвечено" : "Unanswered"}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Bookmark className="w-3.5 h-3.5 text-red-500 fill-red-500 shrink-0" />
                    <span>{lang === "ky" ? "Белгиленген" : lang === "ru" ? "На проверку" : "For Review"}</span>
                  </div>
                </div>

                {/* The Grid: grid grid-cols-6 gap-3 p-6 */}
                <div className="grid grid-cols-6 gap-3 p-6 max-h-[300px] overflow-y-auto">
                  {questionIds.map((qId, idx) => {
                    const isCurrent = currentIndex === idx;
                    const ans = answers[qId];
                    const isAnswered = ans && Boolean(ans.selectedOptionId);
                    const isFlagged = ans && Boolean(ans.flagged);

                    return (
                      <button
                        key={qId}
                        type="button"
                        onClick={() => {
                          setCurrentIndex(idx);
                          setIsGridOpen(false);
                        }}
                        className={`relative w-10 h-10 flex items-center justify-center font-sans font-medium text-blue-700 cursor-pointer transition-all ${
                          isCurrent
                            ? "border-2 border-black rounded-sm bg-white font-bold"
                            : isAnswered
                            ? "border-2 border-solid border-gray-400 rounded-sm bg-blue-50/20 hover:border-blue-500"
                            : "border-2 border-dashed border-gray-400 rounded-sm hover:border-gray-600"
                        }`}
                      >
                        {/* Map pin icon for Current */}
                        {isCurrent && (
                          <span className="absolute -top-3 left-1/2 -translate-x-1/2 pointer-events-none">
                            <MapPin className="w-3.5 h-3.5 text-black fill-black" />
                          </span>
                        )}

                        {/* Red Bookmark icon for Flagged */}
                        {isFlagged && (
                          <span className="absolute -top-1.5 -right-1.5 pointer-events-none">
                            <Bookmark className="w-3.5 h-3.5 text-red-500 fill-red-500" />
                          </span>
                        )}

                        <span className="text-sm font-semibold">{idx + 1}</span>
                      </button>
                    );
                  })}
                </div>

                {/* Review Page Button */}
                <div className="border-t border-gray-100 pt-3 pb-4 text-center bg-white">
                  <button
                    type="button"
                    onClick={() => {
                      setIsGridOpen(false);
                      setCurrentIndex(activeQuestions.length - 1);
                    }}
                    className="text-blue-600 font-sans font-medium text-sm pb-1 hover:underline cursor-pointer"
                  >
                    {lang === "ky" ? "Кароо барагына өтүү" : lang === "ru" ? "Перейти к странице обзора" : "Go to Review Page"}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Right Section: Back (transparent) and Next (pill) */}
        <div className="flex items-center gap-2">
          {currentIndex > 0 && (
            <button
              type="button"
              onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
              disabled={isTimeExpiredModalOpen}
              className="text-gray-700 font-sans font-medium text-sm px-4 py-2 hover:text-gray-900 transition-colors cursor-pointer disabled:opacity-40"
            >
              {lang === "ky" ? "Артка" : "Назад"}
            </button>
          )}

          <button
            type="button"
            onClick={() => {
              if (currentIndex < activeQuestions.length - 1) {
                setCurrentIndex((prev) => prev + 1);
              } else {
                if (isSubjectTest) {
                  handleSubmitFinalTest();
                } else {
                  handleSectionTimeExpiredOrFinish();
                }
              }
            }}
            disabled={isSubmittingFinal || isTimeExpiredModalOpen}
            className="bg-blue-600 text-white px-8 py-2 rounded-full font-sans font-medium text-sm hover:bg-blue-700 transition-colors cursor-pointer shadow-xs disabled:opacity-50 flex items-center gap-1.5"
          >
            {isSubmittingFinal && currentIndex === activeQuestions.length - 1 && (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            )}
            <span>
              {currentIndex < activeQuestions.length - 1
                ? (lang === "ky" ? "Кийинки" : "Далее")
                : isSubjectTest || isFinalSection
                ? (lang === "ky" ? "Экзаменди аяктоо" : "Завершить тест")
                : (lang === "ky" ? "Кийинки бөлүм" : "Следующий раздел")}
            </span>
          </button>
        </div>
      </footer>
    </div>
  );
}

export default function ExamRunnerPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-[70vh] flex flex-col items-center justify-center gap-3 text-slate-400">
          <RefreshCw className="w-8 h-8 animate-spin text-indigo-600" />
          <span className="text-sm font-medium">Жүктөлүүдө...</span>
        </div>
      }
    >
      <ExamRunnerContent />
    </Suspense>
  );
}
