// Student UI U7 (docs/phases/STUDENT_UI_DESIGN.md §3.5, §4.4): pure helpers of the syllabus and the lesson page:
// the lessons in course order, where each one opens, the progress counts and the click-to-load player's address.
// Locks come from the server (`ItemStudentOut.locked`, the module state); nothing here unlocks anything.
// F5b (COURSE_LESSONS_DESIGN 4, 8): done, progress and "up next" are the server's; these helpers only read them.
import type { ItemRefOut, ItemStudentOut, ModuleStudentOut, ModulesStudentOut, VideoOut } from "@/lib/lms/modulesTypes";
import { itemHref } from "./moduleUi";

export interface LessonRef {
  mod: ModuleStudentOut;
  item: ItemStudentOut;
  /** Position among all lessons of the course (0-based). */
  index: number;
}

/** Every item but headers, module by module, in order. */
export function lessonList(modules: ModuleStudentOut[]): LessonRef[] {
  const out: LessonRef[] = [];
  for (const mod of modules) {
    for (const item of mod.items) {
      if (item.kind !== "header") out.push({ mod, item, index: out.length });
    }
  }
  return out;
}

/** A gating-exempt exam (ORT preset) opens inside a locked module; every other row of a locked module is locked. */
export function isExempt(mod: ModuleStudentOut, item: ItemStudentOut): boolean {
  return mod.state === "locked" && !item.locked && item.kind === "assignment" && !!item.link?.assignment_id;
}

export function isLocked(mod: ModuleStudentOut, item: ItemStudentOut): boolean {
  return item.locked || (mod.state === "locked" && !isExempt(mod, item));
}

/** `/courses/{c}/modules/{m}/items/{i}`: the lesson page. */
export function lessonRoute(base: string, moduleId: string, itemId: string): string {
  return `${base}/modules/${moduleId}/items/${itemId}`;
}

/** Where a row opens from the overview CTA, the outline and the prev / next links: an assignment its own route (the
 * lobby); every lesson (video, link, page, file) and every locked row the lesson page (F5b: pages render inline). */
export function lessonHref(base: string, ref: LessonRef): string {
  const { mod, item } = ref;
  if (!isLocked(mod, item) && item.kind === "assignment") {
    const href = itemHref(base, item.kind, item.link);
    if (href) return href;
  }
  return lessonRoute(base, mod.id, item.id);
}

/** F5b (COURSE_LESSONS_DESIGN 5): the row is closed by the Pro tier (a module rule would give `module`). */
export function isAccessLocked(item: ItemStudentOut): boolean {
  return item.locked_reason === "access_required";
}

/** F5b (design 4): done as the server decides it; an older backend without `done` falls back to the requirement. */
export function isDone(item: ItemStudentOut): boolean {
  return item.done ?? !!item.requirement?.met;
}

/** Done / total / duration of the course (the server's `progress`, else counted over the same rows). */
export function courseProgress(data: ModulesStudentOut, lessons: LessonRef[]): { done: number; total: number; duration_s: number } {
  if (data.progress) return data.progress;
  return {
    done: lessons.filter((l) => isDone(l.item)).length,
    total: lessons.length,
    duration_s: lessons.reduce((a, l) => a + (l.item.duration_s ?? 0), 0),
  };
}

/** The row "Продолжить" opens: the server's `up_next` when it is an open row, else the first open row not done. */
export function nextOpen(lessons: LessonRef[], upNext: ItemRefOut | null): LessonRef | null {
  if (upNext) {
    const hit = lessons.find((l) => l.item.id === upNext.item_id && l.mod.id === upNext.module_id);
    if (hit && !isLocked(hit.mod, hit.item)) return hit;
  }
  return lessons.find((l) => !isLocked(l.mod, l.item) && !isDone(l.item)) ?? null;
}

/** The overview banner's one state (design 4): no rows yet, a next row, only Pro rows left, only rule-locked rows left
 * (they open later), or everything done. */
export type OverviewState =
  | { kind: "empty" } | { kind: "next"; next: LessonRef } | { kind: "pro" } | { kind: "later" } | { kind: "finished" };

export function overviewState(lessons: LessonRef[], upNext: ItemRefOut | null): OverviewState {
  if (lessons.length === 0) return { kind: "empty" };
  const next = nextOpen(lessons, upNext);
  if (next) return { kind: "next", next };
  const left = lessons.filter((l) => isLocked(l.mod, l.item) && !isDone(l.item));
  if (left.some((l) => isAccessLocked(l.item))) return { kind: "pro" };
  if (left.length > 0) return { kind: "later" };
  return { kind: "finished" };
}

type Translate =(key: string, vars?: Record<string, string | number>) => string;

/** "6 мин", "1 ч", "1 ч 10 мин" (whole minutes, at least one); empty without a duration. */
export function formatDuration(seconds: number | null | undefined, t: Translate): string {
  if (!seconds || seconds <= 0) return "";
  const total = Math.max(1, Math.round(seconds / 60));
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return t("modules.overview.durationMin", { n: m });
  if (m === 0) return t("modules.overview.durationHours", { h });
  return t("modules.overview.durationHoursMin", { h, m });
}

const YT_ID = /^[A-Za-z0-9_-]{11}$/;
const VIMEO_ID = /^[0-9]{1,12}$/;

/** The provider's own player address built from the validated id (never the stored URL); null when invalid. */
export function videoEmbedUrl(video: VideoOut | null | undefined): string | null {
  if (!video) return null;
  if (video.provider === "youtube" && YT_ID.test(video.id)) {
    return `https://www.youtube-nocookie.com/embed/${video.id}?autoplay=1&rel=0`;
  }
  if (video.provider === "vimeo" && VIMEO_ID.test(video.id)) {
    return `https://player.vimeo.com/video/${video.id}?autoplay=1&dnt=1`;
  }
  return null;
}
