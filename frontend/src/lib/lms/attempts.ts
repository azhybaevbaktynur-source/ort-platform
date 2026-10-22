import { getAuthHeader } from "@/lib/api";
import { LmsApiError, lmsFetch } from "./client";
import type {
  AnswerIn, AttemptContent, AttemptResultOut, AttemptState, MyAttemptOut, ReviewOut, SaveOut, StartIn,
  SubmitIn, SubmitOut,
} from "./attemptTypes";

const e = encodeURIComponent;

export const startAttempt = (courseId: string, assessmentId: string, body: StartIn = {}) =>
  lmsFetch<AttemptState>(`/courses/${e(courseId)}/assessments/${e(assessmentId)}/attempts`, { method: "POST", body });
export const listMyAttempts = (courseId: string, assessmentId: string) =>
  lmsFetch<MyAttemptOut[]>(`/courses/${e(courseId)}/assessments/${e(assessmentId)}/attempts/mine`);
export const getAttempt = (attemptId: string, signal?: AbortSignal) =>
  lmsFetch<AttemptState>(`/attempts/${e(attemptId)}`, { signal });
export const saveAnswers = (attemptId: string, answers: AnswerIn[], signal?: AbortSignal) =>
  lmsFetch<SaveOut>(`/attempts/${e(attemptId)}/answers`, { method: "PUT", body: { answers }, signal });
export const closeSection = (attemptId: string, pos: number) =>
  lmsFetch<AttemptState>(`/attempts/${e(attemptId)}/sections/${pos}/close`, { method: "POST" });
export const submitAttempt = (attemptId: string, body: SubmitIn = {}) =>
  lmsFetch<SubmitOut>(`/attempts/${e(attemptId)}/submit`, { method: "POST", body });
export const getAttemptResult = (attemptId: string) => lmsFetch<AttemptResultOut>(`/attempts/${e(attemptId)}/result`);
export const getAttemptReview = (attemptId: string) => lmsFetch<ReviewOut>(`/attempts/${e(attemptId)}/review`);

/**
 * Shared content payload. Immutable per (version, language[, section]), so the browser HTTP cache (ETag) is used.
 * Forward-only attempts point `content_url` at the current section; refetch when it changes.
 * `content_url` may be absolute, start with `/api/`, or be relative to the API base; all three work.
 */
export async function getAttemptContent(state: Pick<AttemptState, "content_url">, signal?: AbortSignal): Promise<AttemptContent> {
  const base = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
  const u = state.content_url;
  const url = /^https?:\/\//.test(u) || u.startsWith("/api/") ? u : `${base}${u.startsWith("/") ? "" : "/"}${u}`;
  let res: Response;
  try {
    res = await fetch(url, { headers: { ...(await getAuthHeader()) }, cache: "default", signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new LmsApiError(0, "network", "Network error");
  }
  if (!res.ok) {
    let code = res.status === 404 ? "attempt_not_found" : res.status === 403 ? "forbidden" : "unknown";
    try {
      const j = await res.json();
      if (j?.error?.code) code = j.error.code;
    } catch { /* ignore */ }
    throw new LmsApiError(res.status, code, `HTTP ${res.status}`);
  }
  return (await res.json()) as AttemptContent;
}

/**
 * Fire-and-forget save for `visibilitychange: hidden` / `pagehide` (fetch keepalive survives navigation).
 * Browsers cap keepalive bodies at 64 KiB; callers skip it for bigger batches.
 */
export async function saveAnswersKeepalive(attemptId: string, answers: AnswerIn[]): Promise<void> {
  const base = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
  const body = JSON.stringify({ answers });
  if (body.length > 60_000) return;
  try {
    await fetch(`${base}/attempts/${encodeURIComponent(attemptId)}/answers`, {
      method: "PUT",
      headers: { ...(await getAuthHeader()), "Content-Type": "application/json" },
      body,
      keepalive: true,
      cache: "no-store",
    });
  } catch { /* the queue stays in localStorage and replays on the next load */ }
}
