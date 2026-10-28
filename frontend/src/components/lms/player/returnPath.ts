"use client";

import { useEffect, useState } from "react";

/**
 * Phase 8b S3 (PHASE_8B_DESIGN 7.2): `?return=<path>` on the player and result URLs (the constructor's "Preview as
 * student" sets it). Only a same-origin path under the current language is accepted (`/<lang>/...`): no scheme, no
 * protocol-relative `//`, no backslash, no control characters. Anything else is ignored, so every ORT and course flow
 * (no `return`) keeps today's links.
 */
export function safeReturnPath(raw: string | null | undefined, lang: string): string | null {
  if (!raw || raw.length > 500) return null;
  if (!raw.startsWith(`/${lang}/`)) return null;
  if (raw.includes("//") || raw.includes("\\")) return null;
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f]/.test(raw)) return null;
  return raw;
}

/** The validated `return` query value of the current URL (read on the client after mount; null when absent). */
export function useReturnPath(lang: string): string | null {
  const [value, setValue] = useState<string | null>(null);
  useEffect(() => {
    try {
      setValue(safeReturnPath(new URLSearchParams(window.location.search).get("return"), lang));
    } catch {
      setValue(null);
    }
  }, [lang]);
  return value;
}

/** `href` with `return=<path>` added to its query (unchanged when there is no return path). */
export function withReturn(href: string, ret: string | null): string {
  if (!ret) return href;
  return `${href}${href.includes("?") ? "&" : "?"}return=${encodeURIComponent(ret)}`;
}
