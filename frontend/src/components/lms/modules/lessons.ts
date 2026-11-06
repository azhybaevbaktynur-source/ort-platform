// Student UI U7 (docs/phases/STUDENT_UI_DESIGN.md §3.5, §4.4): pure helpers of the syllabus and the lesson page:
// the lessons in course order, where each one opens, the progress counts and the click-to-load player's address.
// Locks come from the server (`ItemStudentOut.locked`, the module state); nothing here unlocks anything.
import type { ItemRefOut, ItemStudentOut, ModuleStudentOut, VideoOut } from "@/lib/lms/modulesTypes";
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

/** Where a lesson opens from the syllabus CTA and the prev / next links: a page keeps `/pages/{id}` (with the lesson
 * so its footer can offer prev / next), an assignment its own route, everything else the lesson page. */
export function lessonHref(base: string, ref: LessonRef): string {
  const { mod, item } = ref;
  if (!isLocked(mod, item)) {
    if (item.kind === "page" && item.link?.page_id) {
      return `${base}/pages/${item.link.page_id}?from=module&m=${encodeURIComponent(mod.id)}&i=${encodeURIComponent(item.id)}`;
    }
    if (item.kind === "assignment") {
      const href = itemHref(base, item.kind, item.link);
      if (href) return href;
    }
  }
  return lessonRoute(base, mod.id, item.id);
}

/** Done/total over the lessons that have a requirement (others have no "done" state). */
export function syllabusProgress(lessons: LessonRef[]): { done: number; total: number } {
  const withReq = lessons.filter((l) => l.item.requirement);
  return { done: withReq.filter((l) => l.item.requirement?.met).length, total: withReq.length };
}

/** The lesson the "Start" / "Continue" button opens: the server's "up next", else the first open lesson while nothing
 * is done yet; null when every lesson with a requirement is done. */
export function nextLesson(lessons: LessonRef[], upNext: ItemRefOut | null): LessonRef | null {
  if (upNext) {
    const hit = lessons.find((l) => l.item.id === upNext.item_id);
    if (hit && !isLocked(hit.mod, hit.item)) return hit;
  }
  const { done, total } = syllabusProgress(lessons);
  if (total > 0 && done >= total) return null;
  return lessons.find((l) => !isLocked(l.mod, l.item) && !l.item.requirement?.met) ?? null;
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
