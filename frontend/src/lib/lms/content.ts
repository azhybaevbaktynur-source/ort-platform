import { getAuthHeader } from "@/lib/api";
import { LmsApiError, lmsFetch } from "./client";
import type { PageOut } from "./types";
import type {
  AssetOut, BankCreateIn, BankOut, BankUpdateIn, MoveDirection, PassageCreateIn, PassageOut,
  PassageSummaryOut, PassageUpdateIn, PassageVersionOut, PassageVersionSummaryOut, QuestionCreateIn,
  QuestionListParams, QuestionStaffOut, QuestionSummaryOut, QuestionUpdateIn, RevertIn,
  StudentQuestionOut, TranslationCreateIn, VersionOut, VersionSummaryOut,
} from "./contentTypes";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const e = encodeURIComponent;
const c = (courseId: string) => `/courses/${e(courseId)}`;

// ---- Banks ----
export const listBanks = (courseId: string, opts: { deleted?: boolean; cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<BankOut>>(`${c(courseId)}/banks`, { params: { deleted: opts.deleted, cursor: opts.cursor, limit: opts.limit } });
export const getBank = (courseId: string, bankId: string) => lmsFetch<BankOut>(`${c(courseId)}/banks/${e(bankId)}`);
export const createBank = (courseId: string, body: BankCreateIn) =>
  lmsFetch<BankOut>(`${c(courseId)}/banks`, { method: "POST", body });
export const updateBank = (courseId: string, bankId: string, body: BankUpdateIn) =>
  lmsFetch<BankOut>(`${c(courseId)}/banks/${e(bankId)}`, { method: "PATCH", body });
export const deleteBank = (courseId: string, bankId: string) =>
  lmsFetch<void>(`${c(courseId)}/banks/${e(bankId)}`, { method: "DELETE" });
export const restoreBank = (courseId: string, bankId: string) =>
  lmsFetch<BankOut>(`${c(courseId)}/banks/${e(bankId)}/restore`, { method: "POST" });

// ---- Questions ----
export const listQuestions = (courseId: string, bankId: string, p: QuestionListParams = {}) =>
  lmsFetch<PageOut<QuestionSummaryOut>>(`${c(courseId)}/banks/${e(bankId)}/questions`, {
    params: {
      q: p.q, type: p.type, language: p.language, section: p.section, topic: p.topic, difficulty: p.difficulty,
      tag: p.tag, passage_id: p.passage_id, deleted: p.deleted, cursor: p.cursor, limit: p.limit,
    },
  });
export const createQuestion = (courseId: string, bankId: string, body: QuestionCreateIn) =>
  lmsFetch<QuestionStaffOut>(`${c(courseId)}/banks/${e(bankId)}/questions`, { method: "POST", body });
export const getQuestion = (courseId: string, questionId: string) =>
  lmsFetch<QuestionStaffOut>(`${c(courseId)}/questions/${e(questionId)}`);
export const updateQuestion = (courseId: string, questionId: string, body: QuestionUpdateIn) =>
  lmsFetch<QuestionStaffOut>(`${c(courseId)}/questions/${e(questionId)}`, { method: "PATCH", body });
export const deleteQuestion = (courseId: string, questionId: string) =>
  lmsFetch<void>(`${c(courseId)}/questions/${e(questionId)}`, { method: "DELETE" });
export const restoreQuestion = (courseId: string, questionId: string) =>
  lmsFetch<QuestionStaffOut>(`${c(courseId)}/questions/${e(questionId)}/restore`, { method: "POST" });
export const moveQuestion = (courseId: string, questionId: string, direction: MoveDirection) =>
  lmsFetch<QuestionSummaryOut>(`${c(courseId)}/questions/${e(questionId)}/move`, { method: "POST", body: { direction } });
export const previewQuestion = (courseId: string, questionId: string, versionId?: string) =>
  lmsFetch<StudentQuestionOut>(`${c(courseId)}/questions/${e(questionId)}/preview`, { params: { version_id: versionId } });

// ---- Question versions ----
export const listQuestionVersions = (courseId: string, questionId: string, opts: { cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<VersionSummaryOut>>(`${c(courseId)}/questions/${e(questionId)}/versions`, { params: opts });
export const getQuestionVersion = (courseId: string, questionId: string, versionId: string) =>
  lmsFetch<VersionOut>(`${c(courseId)}/questions/${e(questionId)}/versions/${e(versionId)}`);
export const revertQuestion = (courseId: string, questionId: string, versionId: string, body: RevertIn) =>
  lmsFetch<QuestionStaffOut>(`${c(courseId)}/questions/${e(questionId)}/versions/${e(versionId)}/revert`, { method: "POST", body });

// ---- Translations ----
export const listTranslations = (courseId: string, questionId: string) =>
  lmsFetch<QuestionSummaryOut[]>(`${c(courseId)}/questions/${e(questionId)}/translations`);
export const addTranslation = (courseId: string, questionId: string, body: TranslationCreateIn) =>
  lmsFetch<QuestionStaffOut>(`${c(courseId)}/questions/${e(questionId)}/translations`, { method: "POST", body });
export const linkTranslation = (courseId: string, questionId: string, otherQuestionId: string) =>
  lmsFetch<void>(`${c(courseId)}/questions/${e(questionId)}/translation-link`, { method: "POST", body: { question_id: otherQuestionId } });
export const unlinkTranslation = (courseId: string, questionId: string) =>
  lmsFetch<void>(`${c(courseId)}/questions/${e(questionId)}/translation-link`, { method: "DELETE" });

// ---- Passages ----
export const listPassages = (courseId: string, bankId: string, opts: { deleted?: boolean; cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<PassageSummaryOut>>(`${c(courseId)}/banks/${e(bankId)}/passages`, { params: opts });
export const createPassage = (courseId: string, bankId: string, body: PassageCreateIn) =>
  lmsFetch<PassageOut>(`${c(courseId)}/banks/${e(bankId)}/passages`, { method: "POST", body });
export const getPassage = (courseId: string, passageId: string) => lmsFetch<PassageOut>(`${c(courseId)}/passages/${e(passageId)}`);
export const updatePassage = (courseId: string, passageId: string, body: PassageUpdateIn) =>
  lmsFetch<PassageOut>(`${c(courseId)}/passages/${e(passageId)}`, { method: "PATCH", body });
export const deletePassage = (courseId: string, passageId: string) =>
  lmsFetch<void>(`${c(courseId)}/passages/${e(passageId)}`, { method: "DELETE" });
export const restorePassage = (courseId: string, passageId: string) =>
  lmsFetch<PassageOut>(`${c(courseId)}/passages/${e(passageId)}/restore`, { method: "POST" });
export const listPassageVersions = (courseId: string, passageId: string, opts: { cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<PassageVersionSummaryOut>>(`${c(courseId)}/passages/${e(passageId)}/versions`, { params: opts });
export const getPassageVersion = (courseId: string, passageId: string, versionId: string) =>
  lmsFetch<PassageVersionOut>(`${c(courseId)}/passages/${e(passageId)}/versions/${e(versionId)}`);
export const revertPassage = (courseId: string, passageId: string, versionId: string, body: RevertIn) =>
  lmsFetch<PassageOut>(`${c(courseId)}/passages/${e(passageId)}/versions/${e(versionId)}/revert`, { method: "POST", body });

// ---- Assets ----
export const listMyAssets = (opts: { cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<AssetOut>>(`/assets`, { params: opts });
export const deleteAsset = (assetId: string) => lmsFetch<void>(`/assets/${e(assetId)}`, { method: "DELETE" });

/** Multipart upload; errors are parsed into LmsApiError exactly like lmsFetch. */
export async function uploadAsset(courseId: string, file: File, visibility: "public" | "private" = "public"): Promise<AssetOut> {
  const form = new FormData();
  form.append("file", file);
  form.append("visibility", visibility);
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${c(courseId)}/assets`, {
      method: "POST",
      headers: { ...(await getAuthHeader()) },
      body: form,
      cache: "no-store",
    });
  } catch {
    throw new LmsApiError(0, "network", "Network error");
  }
  const text = await res.text();
  let data: unknown = undefined;
  if (text) {
    try { data = JSON.parse(text); } catch { data = undefined; }
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | undefined)?.error;
    if (err && typeof err === "object" && typeof err.code === "string") {
      throw new LmsApiError(res.status, err.code, err.message || err.code, err.details || {});
    }
    const code = res.status === 413 ? "image_too_large" : res.status === 403 ? "forbidden" : res.status === 404 ? "not_found" : "unknown";
    throw new LmsApiError(res.status, code, `HTTP ${res.status}`);
  }
  return data as AssetOut;
}
