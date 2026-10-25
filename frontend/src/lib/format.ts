/**
 * Date helpers for API timestamps (H2 guard, docs/phases/PHASE_6_DESIGN.md §8.2).
 * The API stores UTC. Some columns serialize without a timezone suffix ("2026-10-25T08:00:00");
 * `new Date()` would read those as local time. A datetime string without `Z` or an offset is
 * therefore treated as UTC. Date-only strings ("2026-10-25") are left as they are.
 */
const HAS_TIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;
const HAS_ZONE = /(?:Z|[+-]\d{2}(?::?\d{2})?)$/i;

export function parseApiDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  let s = value.trim();
  if (HAS_TIME.test(s) && !HAS_ZONE.test(s)) s = `${s.replace(" ", "T")}Z`;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Local date and time, or "" for an empty/invalid value. */
export function fmtApiDateTime(value: string | null | undefined, locale?: string): string {
  const d = parseApiDate(value);
  return d ? d.toLocaleString(locale) : "";
}

/** Local date only, or "" for an empty/invalid value. */
export function fmtApiDate(value: string | null | undefined, locale?: string): string {
  const d = parseApiDate(value);
  return d ? d.toLocaleDateString(locale) : "";
}
