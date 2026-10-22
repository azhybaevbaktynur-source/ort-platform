import type { Lang, LocalizedText } from "./types";

/** Pick text for the UI language, then the course default language, then any non-empty value. */
export function pickLocalized(
  text: LocalizedText | null | undefined,
  uiLang: Lang,
  defaultLang?: Lang,
): string {
  if (!text) return "";
  const direct = text[uiLang];
  if (direct && direct.trim()) return direct;
  if (defaultLang) {
    const d = text[defaultLang];
    if (d && d.trim()) return d;
  }
  for (const v of Object.values(text)) {
    if (v && v.trim()) return v;
  }
  return "";
}

/** Trim values and drop empty or out-of-language entries before sending to the API. */
export function cleanLocalized(v: LocalizedText, langs: Lang[]): LocalizedText {
  const out: LocalizedText = {};
  for (const l of langs) {
    const s = (v[l] ?? "").trim();
    if (s) out[l] = s;
  }
  return out;
}
