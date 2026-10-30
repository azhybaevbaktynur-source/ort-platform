// Phase 9 S4: enrollment form builder (docs/phases/PHASE_9_DESIGN.md §2.4, §4.6, §5).
import { lmsFetch } from "./client";
import type { EnrollmentFormIn, EnrollmentFormOut, FormStatus } from "./types";

export interface EnrollmentFormSummaryOut {
  id: string;
  version: number;
  status: FormStatus;
  answered: boolean;
  field_count: number;
  created_at: string;
  activated_at: string | null;
  retired_at: string | null;
}

export const FIELDS_PER_FORM_MAX = 25;
export const OPTIONS_PER_FIELD_MAX = 20;
export const FIELD_KEY_RE = /^[a-z][a-z0-9_]{0,39}$/;
export const TEXT_LIMITS = { short_text: { def: 200, max: 500 }, long_text: { def: 1000, max: 2000 } } as const;

const enc = encodeURIComponent;
const base = (courseId: string) => `/courses/${enc(courseId)}/enrollment-forms`;

export const listFormVersions = (courseId: string) => lmsFetch<EnrollmentFormSummaryOut[]>(base(courseId));
export const getForm = (courseId: string, formId: string) =>
  lmsFetch<EnrollmentFormOut>(`${base(courseId)}/${enc(formId)}`);
export const createFormDraft = (courseId: string, body: EnrollmentFormIn) =>
  lmsFetch<EnrollmentFormOut>(base(courseId), { method: "POST", body });
export const updateForm = (courseId: string, formId: string, body: EnrollmentFormIn) =>
  lmsFetch<EnrollmentFormOut>(`${base(courseId)}/${enc(formId)}`, { method: "PATCH", body });
export const deleteFormDraft = (courseId: string, formId: string) =>
  lmsFetch<void>(`${base(courseId)}/${enc(formId)}`, { method: "DELETE" });
export const activateForm = (courseId: string, formId: string) =>
  lmsFetch<EnrollmentFormOut>(`${base(courseId)}/${enc(formId)}/activate`, { method: "POST" });
export const newFormVersion = (courseId: string, formId: string) =>
  lmsFetch<EnrollmentFormOut>(`${base(courseId)}/${enc(formId)}/new-version`, { method: "POST" });

/** A slug from a label: lowercase latin letters, digits and underscores, starting with a letter. */
export function keyFromLabel(label: string, taken: Set<string>): string {
  const translit: Record<string, string> = {
    а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z", и: "i", й: "i", к: "k", л: "l", м: "m",
    н: "n", ң: "n", о: "o", ө: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ү: "u", ф: "f", х: "h", ц: "c", ч: "ch",
    ш: "sh", щ: "sh", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
  };
  const raw = label.toLowerCase().split("").map((ch) => translit[ch] ?? ch).join("");
  let key = raw.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 32);
  if (!/^[a-z]/.test(key)) key = `field_${key}`.replace(/_+$/g, "");
  if (!key) key = "field";
  let candidate = key;
  for (let i = 2; taken.has(candidate); i += 1) candidate = `${key.slice(0, 36)}_${i}`;
  return candidate;
}
