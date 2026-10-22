import type { StudentChoiceOut } from "@/lib/lms/contentTypes";
import type {
  AttemptContent, AttemptItemState, AttemptState, StudentPassage, StudentQuestion,
} from "@/lib/lms/attemptTypes";

export type ResponseObj = Record<string, unknown> | null;

/** Whether a stored response counts as "answered" for the palette and the submit summary. */
export function isAnswered(type: StudentQuestion["type"] | undefined, response: ResponseObj | undefined): boolean {
  if (!response) return false;
  switch (type) {
    case "single_choice": return typeof response.choice_id === "string" && response.choice_id !== "";
    case "multiple_answers": return Array.isArray(response.choice_ids) && response.choice_ids.length > 0;
    case "true_false": return typeof response.value === "boolean";
    case "comparison": return typeof response.choice === "string" && response.choice !== "";
    case "numeric": return typeof response.value === "string" && response.value.trim() !== "";
    case "short_text":
    case "essay": return typeof response.text === "string" && response.text.trim() !== "";
    default: return false;
  }
}

export function itemQuestion(state: AttemptState, content: AttemptContent, item: AttemptItemState): StudentQuestion | undefined {
  if (!item.qv) return undefined;
  return content.questions[item.qv] ?? state.extra_questions?.[item.qv];
}

/**
 * Forward-only attempts load content one section at a time; keep what earlier sections already delivered
 * (display only) and add the new section's questions, passages and images.
 */
export function mergeContent(prev: AttemptContent | null, next: AttemptContent): AttemptContent {
  if (!prev || prev.version_id !== next.version_id || prev.language !== next.language) return next;
  return {
    ...next,
    questions: { ...prev.questions, ...next.questions },
    passages: { ...prev.passages, ...next.passages },
    image_urls: Array.from(new Set([...prev.image_urls, ...next.image_urls])),
  };
}

export function itemPassage(content: AttemptContent, item: AttemptItemState, q: StudentQuestion | undefined): StudentPassage | null {
  if (item.pv && content.passages[item.pv]) return content.passages[item.pv];
  return q?.passage ?? null;
}

/** Choices in the attempt's display order (`choice_order`), falling back to payload order. */
export function orderedChoices(q: StudentQuestion, order: string[] | null): StudentChoiceOut[] {
  const choices = q.data.choices ?? [];
  if (!order || order.length === 0) return choices;
  const byId = new Map(choices.map((c) => [c.id, c]));
  const out: StudentChoiceOut[] = [];
  for (const id of order) {
    const c = byId.get(id);
    if (c) { out.push(c); byId.delete(id); }
  }
  for (const c of byId.values()) out.push(c);
  return out;
}

export const letter = (i: number) => String.fromCharCode(65 + (i % 26));

export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  const mm = String(m).padStart(2, "0");
  const sec = String(ss).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${sec}` : `${mm}:${sec}`;
}

export function isTypingTarget(el: EventTarget | null): boolean {
  const n = el as HTMLElement | null;
  if (!n || !n.tagName) return false;
  const tag = n.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || n.isContentEditable;
}
