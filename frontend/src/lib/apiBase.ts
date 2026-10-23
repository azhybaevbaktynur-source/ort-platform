/**
 * Base URL for every backend call. Unset: relative "/api/v1" (Next.js rewrites proxy it to FastAPI).
 * NEXT_PUBLIC_API_URL may be the bare backend origin (as on Vercel) or already end in /api/v1; both work,
 * the same way next.config.ts normalizes it for the rewrite.
 */
function normalize(raw: string | undefined): string {
  const base = (raw || "").trim().replace(/\/+$/, "");
  if (!base) return "/api/v1";
  return base.endsWith("/api/v1") ? base : `${base}/api/v1`;
}

export const API_BASE_URL = normalize(process.env.NEXT_PUBLIC_API_URL);
