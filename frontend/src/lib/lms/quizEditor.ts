// API client of the Phase 7c quiz editor (PHASE_7C_DESIGN 6.1).
import { lmsFetch } from "./client";
import { listMyAssets } from "./content";
import type { PageOut } from "./types";
import type { BankOut, ImageOut, QuestionStaffOut } from "./contentTypes";
import type {
  CardPayload, CommitIn, CommitOut, CopyToBankIn, DraftCreateIn, DraftOut, DraftUpdateIn, QuestionUsageOut,
  QuizQuestionCreateIn,
} from "./quizEditorTypes";

const e = encodeURIComponent;
const c = (courseId: string) => `/courses/${e(courseId)}`;
const a = (courseId: string, aid: string) => `${c(courseId)}/assessments/${e(aid)}`;

export const createQuizQuestion = (courseId: string, aid: string, body: QuizQuestionCreateIn) =>
  lmsFetch<CommitOut>(`${a(courseId, aid)}/questions`, { method: "POST", body });
export const createDraft = (courseId: string, aid: string, body: DraftCreateIn, opts: { keepalive?: boolean } = {}) =>
  lmsFetch<DraftOut>(`${a(courseId, aid)}/drafts`, { method: "POST", body, ...opts });
export const updateDraft = (courseId: string, aid: string, draftId: string, body: DraftUpdateIn, opts: { keepalive?: boolean } = {}) =>
  lmsFetch<DraftOut>(`${a(courseId, aid)}/drafts/${e(draftId)}`, { method: "PUT", body, ...opts });
export const deleteDraft = (courseId: string, aid: string, draftId: string) =>
  lmsFetch<void>(`${a(courseId, aid)}/drafts/${e(draftId)}`, { method: "DELETE" });
export const commitDraft = (courseId: string, aid: string, draftId: string, body: CommitIn) =>
  lmsFetch<CommitOut>(`${a(courseId, aid)}/drafts/${e(draftId)}/commit`, { method: "POST", body });
export const getQuestionUsage = (courseId: string, questionId: string) =>
  lmsFetch<QuestionUsageOut>(`${c(courseId)}/questions/${e(questionId)}/usage`);
export const copyToBank = (courseId: string, questionId: string, body: CopyToBankIn) =>
  lmsFetch<QuestionStaffOut>(`${c(courseId)}/questions/${e(questionId)}/copy-to-bank`, { method: "POST", body });

/**
 * Shared banks of the course only (PHASE_7C_DESIGN 16: a quiz bank is private to its quiz, so pickers never offer
 * one). Uses the `kind` filter of `GET /courses/{id}/banks` directly so this slice does not touch `content.ts`.
 */
export const listSharedBanks = (courseId: string, opts: { cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<BankOut>>(`${c(courseId)}/banks`, { params: { kind: "shared", cursor: opts.cursor, limit: opts.limit } });

// ---- Image urls of draft payloads ----
// A draft stores `image_asset_id` only. Urls seen in this session are remembered; unknown ids are looked up once in
// the teacher's own assets (the images they uploaded), so a reloaded draft still shows its pictures.
const imageCache = new Map<string, ImageOut>();
let assetsLoaded = false;

export function rememberImage(img: ImageOut | null | undefined): void {
  if (img && img.asset_id && img.url) imageCache.set(img.asset_id, img);
}

function payloadAssetIds(p: CardPayload): string[] {
  const ids: string[] = [];
  if (p.image_asset_id) ids.push(p.image_asset_id);
  const choices = (p.data as { choices?: unknown }).choices;
  if (Array.isArray(choices)) {
    for (const ch of choices) {
      const id = (ch as { image_asset_id?: unknown })?.image_asset_id;
      if (typeof id === "string" && id) ids.push(id);
    }
  }
  return ids;
}

/** Returns a lookup for the payload's images (url "" when it cannot be resolved; the id is kept either way). */
export async function resolvePayloadImages(p: CardPayload): Promise<(assetId: string) => ImageOut> {
  const missing = payloadAssetIds(p).filter((id) => !imageCache.has(id));
  if (missing.length && !assetsLoaded) {
    assetsLoaded = true;
    try {
      const page = await listMyAssets({ limit: 100 });
      for (const as of page.items) if (as.url) imageCache.set(as.id, { asset_id: as.id, url: as.url, sha256: as.sha256 });
    } catch {
      assetsLoaded = false;
    }
  }
  return (id: string) => imageCache.get(id) ?? { asset_id: id, url: "" };
}
