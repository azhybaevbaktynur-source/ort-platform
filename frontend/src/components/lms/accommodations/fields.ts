/** Phase 7a S5: whole-number fields of the accommodation and exception forms. */

/** "" -> null; a whole number within 0..max -> that number; anything else -> NaN. */
export function parseWhole(s: string, max: number): number | null {
  const v = s.trim();
  if (!v) return null;
  if (!/^\d+$/.test(v)) return Number.NaN;
  const n = Number(v);
  return n >= 0 && n <= max ? n : Number.NaN;
}

export const isBad = (n: number | null) => n !== null && Number.isNaN(n);

export const wholeText = (n: number | null | undefined) => (n === null || n === undefined ? "" : String(n));
