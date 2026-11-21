/*
 * Lesson course requests R5 / C4 (docs/phases/LESSON_COURSE_REQUESTS.md): option letters for display.
 * The real ORT labels options А Б В Г Д, and explanations say «Правильный ответ: В», so ru and ky content shows
 * Cyrillic letters; en content keeps Latin. Stored keys (choice ids, comparison A–D) and keyboard keys never change.
 */
const CYRILLIC: Record<string, string> = { A: "А", B: "Б", C: "В", D: "Г", E: "Д" };

/** Display letter for an option: a stored key ("A"…"E") or a zero-based display index, in the content language. */
export function optionLabel(keyOrIndex: string | number, language?: string | null): string {
  const latin = typeof keyOrIndex === "number" ? String.fromCharCode(65 + (keyOrIndex % 26)) : keyOrIndex;
  if (language === "ru" || language === "ky") return CYRILLIC[latin.toUpperCase()] ?? latin;
  return latin;
}
