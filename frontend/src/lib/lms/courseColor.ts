// UX rework (UX_REWORK_DESIGN C): the colored band of a dashboard course card. Fixed palette, keyed on a hash of the
// course id, so a course keeps its color everywhere. Every color passes AA with white text (`courseColor.check.ts`).
export const COURSE_COLORS = [
  "#1d4ed8", // blue
  "#0f766e", // teal
  "#7c3aed", // violet
  "#be185d", // pink
  "#b45309", // amber
  "#15803d", // green
  "#0369a1", // sky
  "#c2410c", // orange
] as const;

/** FNV-1a over the id: stable across sessions and well spread for UUIDs. */
export function courseColor(courseId: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < courseId.length; i++) {
    h ^= courseId.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return COURSE_COLORS[(h >>> 0) % COURSE_COLORS.length];
}
