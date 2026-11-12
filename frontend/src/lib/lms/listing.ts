/**
 * Step 3b S2 (CATALOG_AND_TEACHERS_DESIGN 2.3, 2.6): the catalog listing as the course settings show it. The server
 * decides (`courses/listing.py`); this only mirrors its D11 preconditions so the request button can say what is
 * missing before it is pressed, and reads the `listing_incomplete` answer when the server knows better.
 * Dependency-free (no imports), so `listing.check.ts` runs without the app.
 */

/** Step 3b S1 (CATALOG_AND_TEACHERS_DESIGN 2.3): `off` → `pending` → `listed` / `declined`; `blocked` by the admin. */
export type ListingState = "off" | "pending" | "listed" | "declined" | "blocked";
/** What a listing request still needs (`listing_incomplete` details.missing, D11). */
export type ListingMissing = "published" | "link_access" | "title" | "description" | "cover_or_content";

/** `ids.LISTING_MISSING` order. */
export const LISTING_MISSING: ListingMissing[] = ["published", "link_access", "title", "description", "cover_or_content"];

/** The fields of `CourseStaffOut` the preconditions read (structural, so this file imports nothing). */
interface ListingInput {
  status: string;
  visibility: string;
  default_language: string;
  title: Partial<Record<string, string>> | null;
  description: Partial<Record<string, string>> | null;
  cover_url?: string | null;
  features?: { modules?: boolean; tests?: boolean; hand_ins?: boolean } | null;
}

/** What a listing request still needs, from the saved course (the server's `missing_items`). Unknown facts (an older
 * payload without `features`) are never reported: the server's answer then decides. */
export function listingMissing(c: ListingInput): ListingMissing[] {
  const missing: ListingMissing[] = [];
  const lang = c.default_language;
  if (c.status !== "published") missing.push("published");
  if (c.visibility !== "catalog") missing.push("link_access");
  if (!((c.title ?? {})[lang] ?? "").trim()) missing.push("title");
  if (!((c.description ?? {})[lang] ?? "").trim()) missing.push("description");
  const f = c.features;
  if (!c.cover_url && f && !(f.modules || f.tests || f.hand_ins)) missing.push("cover_or_content");
  return missing;
}

/** `details.missing` of a 422 `listing_incomplete`, in `LISTING_MISSING` order; null for any other error. */
export function missingFromError(error: unknown): ListingMissing[] | null {
  const e = error as { code?: string; details?: { missing?: unknown } } | null;
  if (!e || e.code !== "listing_incomplete") return null;
  const raw = Array.isArray(e.details?.missing) ? (e.details!.missing as unknown[]) : [];
  return LISTING_MISSING.filter((m) => raw.includes(m));
}

/** The buttons course staff get in each state (§2.6); a blocked course has none. */
export function listingActions(state: ListingState): ("request" | "withdraw" | "remove" | "resend")[] {
  if (state === "off") return ["request"];
  if (state === "pending") return ["withdraw"];
  if (state === "listed") return ["remove"];
  if (state === "declined") return ["resend"];
  return [];
}

/** The badge tone of a listing state (settings block, Admin → Курсы). */
export const LISTING_TONE: Record<ListingState, "neutral" | "info" | "success" | "warning" | "danger"> = {
  off: "neutral", pending: "info", listed: "success", declined: "warning", blocked: "danger",
};
