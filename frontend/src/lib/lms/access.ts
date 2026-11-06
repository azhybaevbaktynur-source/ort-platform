// S3 free and paid exams (docs/phases/S3_ACCESS_DESIGN.md): the student's own pass and the platform admin's codes,
// passes and paid/free toggles. Codes are shown in full only by the reveal and export calls.
import { getAuthHeader } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";
import { LmsApiError, lmsFetch } from "./client";
import type { LocalizedText, PageOut } from "./types";

const enc = encodeURIComponent;
const post = <T,>(path: string, body?: unknown) => lmsFetch<T>(path, { method: "POST", body: body ?? {} });
const A = "/platform/access";

// ------------------------------------------------------------------ student

// F6a Pro (docs/phases/SUBSCRIPTION_DESIGN.md): a plan is only the length a pass was granted or bought with.
export type PlanId = "month_1" | "month_3" | "season";
export type PassSource = "code" | "admin" | "payment";

export interface MyAccessOut {
  active: boolean;
  ends_at: string | null;
  scope: "all";
  practice_free: boolean;
  /** Of the pass that ends the chain; null when inactive (or a legacy, voucher or custom-length pass). */
  plan: PlanId | null;
  /** Whole days left, rounded up; 0 when inactive. */
  days_left: number;
  source: PassSource | null;
}
export interface RedeemOut extends MyAccessOut { pass_ends_at: string }

export interface OfferPlanOut {
  id: PlanId;
  days: number | null;
  /** The season plan: valid all that day (Asia/Bishkek). */
  season_end: string | null;
  /** null: the owner set no price, show none. */
  price_kgs: number | null;
  /** The chain end after this plan. */
  new_ends_at: string;
}
export interface HowToPay { ru: string; ky: string; en: string }
export interface OfferOut {
  /** The season plan is listed only when a season end is set, not passed, and later than the current end. */
  plans: OfferPlanOut[];
  includes: ("tests" | "practice" | "lessons")[];
  practice_free: boolean;
  /** ky/en fall back to ru; empty: show the `access.howToPay` placeholder. */
  how_to_pay: HowToPay;
  season_end: string | null;
  status: { active: boolean; ends_at: string | null; plan: PlanId | null; days_left: number; source: PassSource | null };
}

export const getMyAccess = () => lmsFetch<MyAccessOut>("/me/access");
export const getMyOffer = () => lmsFetch<OfferOut>("/me/access/offer");
export const redeemCode = (code: string) => post<RedeemOut>("/me/access/redeem", { code });

/** "until" date of a pass: the last minute it is valid, in Bishkek time (a pass ends at the start of its last
 *  minute's next one, e.g. 31 May 24:00 shows as 31 May, 23:59). */
export function fmtPassEnd(iso: string | null, lang: string, withTime = true): string {
  if (!iso) return "";
  const d = new Date(new Date(iso).getTime() - 60_000);
  if (Number.isNaN(d.getTime())) return "";
  const opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "long", year: "numeric", timeZone: "Asia/Bishkek" };
  if (withTime) Object.assign(opts, { hour: "2-digit", minute: "2-digit" });
  try {
    return d.toLocaleString(lang === "en" ? "en-GB" : lang, opts);
  } catch {
    return d.toISOString().slice(0, 10);
  }
}

/** A pass's start or end as a short date and time in Bishkek time (dd.mm.yyyy, hh:mm); an end shows its last minute. */
export function fmtPassShort(iso: string | null, lang: string, end = false): string {
  if (!iso) return "";
  const d = new Date(new Date(iso).getTime() - (end ? 60_000 : 0));
  if (Number.isNaN(d.getTime())) return "";
  try {
    return d.toLocaleString(lang === "en" ? "en-GB" : lang, {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Bishkek" });
  } catch {
    return d.toISOString().slice(0, 16).replace("T", " ");
  }
}

/** The format the admin and the student see: XXXX-XXXX-XXXX (input is free; the server normalizes). */
export const CODE_PATTERN_LENGTH = 14;

// ------------------------------------------------------------------ admin: batches and codes

export type CodeStatus = "unused" | "given" | "redeemed" | "revoked";

export interface BatchOut {
  id: string;
  label: string;
  duration_days: number | null;
  ends_on: string | null;
  count: number;
  note: string | null;
  created_at: string;
  created_by: string | null;
  revoked_at: string | null;
  unused: number;
  given: number;
  redeemed: number;
  revoked: number;
}
export interface BatchCreateIn { label: string; count: number; duration_days?: number; ends_on?: string; note?: string }
export interface CodeOut {
  id: string;
  batch_id: string;
  position: number;
  last4: string;
  status: CodeStatus;
  given_at: string | null;
  given_note: string | null;
  redeemed_at: string | null;
  redeemed_by_id: string | null;
  redeemed_by_name: string | null;
  redeemed_by_email: string | null;
  revoked_at: string | null;
}

export const listBatches = (cursor?: string | null, limit = 25) =>
  lmsFetch<PageOut<BatchOut>>(`${A}/batches`, { params: { cursor, limit } });
export const getBatch = (id: string) => lmsFetch<BatchOut>(`${A}/batches/${enc(id)}`);
export const createBatch = (body: BatchCreateIn) => post<BatchOut>(`${A}/batches`, body);
export const revokeBatch = (id: string, reason: string) => post<BatchOut>(`${A}/batches/${enc(id)}/revoke`, { reason });
export const listCodes = (batchId: string, p: { status?: CodeStatus | ""; cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<CodeOut>>(`${A}/batches/${enc(batchId)}/codes`, { params: { limit: 50, ...p } });
export const revealCode = (id: string) => post<{ code: string }>(`${A}/codes/${enc(id)}/reveal`);
export const markGiven = (id: string, note: string) => post<CodeOut>(`${A}/codes/${enc(id)}/given`, { note: note || null });

/** CSV of the batch's codes nobody redeemed (audited); returns the file name and the text. */
export async function exportBatch(id: string): Promise<{ name: string; blob: Blob }> {
  const res = await fetch(`${API_BASE_URL}${A}/batches/${enc(id)}/export`, {
    method: "POST", headers: { ...(await getAuthHeader()) }, cache: "no-store",
  });
  if (!res.ok) {
    let code = "unknown";
    try { code = (await res.json())?.error?.code ?? code; } catch { /* not JSON */ }
    throw new LmsApiError(res.status, code, `HTTP ${res.status}`);
  }
  const disposition = res.headers.get("content-disposition") || "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] || "codes.csv";
  return { name, blob: await res.blob() };
}

// ------------------------------------------------------------------ admin: a person's passes

export interface PassOut {
  id: string;
  scope: string;
  starts_at: string;
  ends_at: string;
  source: PassSource;
  plan: PlanId | null;
  code_last4: string | null;
  granted_by: string | null;
  reason: string | null;
  revoked_at: string | null;
  revoked_by: string | null;
  created_at: string;
  active: boolean;
}
export interface RedemptionOut { code_id: string; last4: string; redeemed_at: string | null; batch_id: string; batch_label: string }
export interface UserAccessOut { active: boolean; ends_at: string | null; passes: PassOut[]; redemptions: RedemptionOut[] }

export const getUserAccess = (userId: string) => lmsFetch<UserAccessOut>(`/platform/users/${enc(userId)}/access`);
/** Exactly one of `plan`, `duration_days`, `ends_on`. Renewal is a grant: an active chain is extended from its end. */
export const grantAccess = (userId: string,
  body: { plan?: PlanId; duration_days?: number; ends_on?: string; reason: string }) =>
  post<UserAccessOut>(`/platform/users/${enc(userId)}/access/grant`, body);
/** Revokes every open pass of the person (one audit event with the reason). */
export const cancelPro = (userId: string, reason: string) =>
  post<UserAccessOut>(`/platform/users/${enc(userId)}/access/cancel`, { reason });
export const revokePass = (passId: string, reason: string) => post<UserAccessOut>(`${A}/passes/${enc(passId)}/revoke`, { reason });

// ------------------------------------------------------------------ admin: F6a Pro list and settings

export type ProStatus = "active" | "expiring" | "expired";
export interface ProRowOut {
  user_id: string;
  name: string | null;
  email: string | null;
  /** The chain end. */
  ends_at: string;
  started_at: string;
  days_left: number;
  active: boolean;
  plan: PlanId | null;
  source: PassSource | null;
}
export interface ProSummaryOut { active: number; expiring: number; expired: number }
export interface ProPrices { month_1: number | null; month_3: number | null; season: number | null }
export interface ProSettingsOut { season_end: string | null; prices: ProPrices; how_to_pay: HowToPay }
export interface ProSettingsIn {
  season_end: string | null;
  prices: Partial<ProPrices>;
  how_to_pay: Partial<HowToPay>;
}

export const listPro = (p: { status?: ProStatus | ""; q?: string; cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<ProRowOut>>(`${A}/pro`, { params: { limit: 25, ...p } });
export const getProSummary = () => lmsFetch<ProSummaryOut>(`${A}/pro/summary`);
export const getProSettings = () => lmsFetch<ProSettingsOut>(`${A}/settings`);
export const putProSettings = (body: ProSettingsIn) =>
  lmsFetch<ProSettingsOut>(`${A}/settings`, { method: "PUT", body });

// ------------------------------------------------------------------ admin: paid/free

export type AccessTier = "free" | "paid";
export interface ExamOut {
  id: string;
  course_id: string;
  course_title: LocalizedText;
  title: LocalizedText;
  preset: string;
  status: string;
  access_tier: AccessTier;
  published_at: string | null;
  created_at: string;
}
export interface PlatformCourseOut { id: string; title: LocalizedText; status: string; practice_free: boolean }
export interface AccessOverviewOut { recent_exams: ExamOut[]; reveals_last_hour: number; reveal_alert: boolean }

export const getAccessOverview = () => lmsFetch<AccessOverviewOut>(`${A}/overview`);
export const listExams = (p: { cursor?: string | null; limit?: number; course_id?: string; tier?: AccessTier | "" } = {}) =>
  lmsFetch<PageOut<ExamOut>>(`${A}/exams`, { params: { limit: 25, ...p } });
export const setExamTier = (id: string, access_tier: AccessTier) =>
  lmsFetch<ExamOut>(`${A}/exams/${enc(id)}`, { method: "PATCH", body: { access_tier } });
export const listPlatformCourses = () => lmsFetch<PlatformCourseOut[]>(`${A}/courses`);
export const setPracticeFree = (id: string, practice_free: boolean) =>
  lmsFetch<PlatformCourseOut>(`${A}/courses/${enc(id)}`, { method: "PATCH", body: { practice_free } });
