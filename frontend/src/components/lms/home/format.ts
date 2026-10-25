/**
 * Phase 6b S6b: date and duration helpers for student screens (UX S6, S9, S15).
 * Server times are UTC (`parseApiDate` reads a missing zone as UTC); shown in local time, without seconds,
 * day first in every UI language.
 */
import { parseApiDate } from "@/lib/format";

type T = (key: string, params?: Record<string, string | number>) => string;

const locale = (lang: string) => (lang === "en" ? "en-GB" : lang);

/** "25/10/2026, 14:05" / "25.10.2026, 14:05" (no seconds), or "" for an empty/invalid value. */
export function fmtShortDateTime(value: string | null | undefined, lang: string): string {
  const d = parseApiDate(value);
  if (!d) return "";
  return d.toLocaleString(locale(lang), { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** True when `value` is in the future but less than 24 hours away (shown in red with a clock icon). */
export function isDueSoon(value: string | null | undefined, now: number = Date.now()): boolean {
  const d = parseApiDate(value);
  if (!d) return false;
  const ms = d.getTime() - now;
  return ms > 0 && ms < 24 * 3600 * 1000;
}

export function isPast(value: string | null | undefined, now: number = Date.now()): boolean {
  const d = parseApiDate(value);
  return !!d && d.getTime() <= now;
}

/** 12900 s -> "3 h 35 min" / "3 ч 35 мин" / "3 саат 35 мүн"; under an hour -> "20 min". */
export function fmtDuration(seconds: number | null | undefined, t: T): string {
  if (!seconds || seconds <= 0) return "";
  const total = Math.round(seconds / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h && m) return t("home.time.hm", { h, m });
  if (h) return t("home.time.h", { h });
  return t("home.time.m", { m: Math.max(m, 1) });
}
