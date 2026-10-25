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

// Phase 6 S8 (UX S3): day first in every UI language; English uses the en-GB order (25/10/2026), not en-US.
const DATE_OPTS: Intl.DateTimeFormatOptions = { day: "2-digit", month: "2-digit", year: "numeric" };
const dayFirst = (locale?: string) => (locale === "en" ? "en-GB" : locale);

/** Local date and time, or "" for an empty/invalid value. */
export function fmtApiDateTime(value: string | null | undefined, locale?: string): string {
  const d = parseApiDate(value);
  return d ? d.toLocaleString(dayFirst(locale)) : "";
}

/** Local date and time without seconds (tables, lists), or "" for an empty/invalid value. Phase 6b S11b. */
export function fmtApiDateTimeShort(value: string | null | undefined, locale?: string): string {
  const d = parseApiDate(value);
  return d ? d.toLocaleString(dayFirst(locale), { ...DATE_OPTS, hour: "2-digit", minute: "2-digit" }) : "";
}

/** Local date only (dd.mm.yyyy / dd/mm/yyyy when a UI language is given), or "" for an empty/invalid value. */
export function fmtApiDate(value: string | null | undefined, locale?: string): string {
  const d = parseApiDate(value);
  if (!d) return "";
  return locale ? d.toLocaleDateString(dayFirst(locale), DATE_OPTS) : d.toLocaleDateString();
}
