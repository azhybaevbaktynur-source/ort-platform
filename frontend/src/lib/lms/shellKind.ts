/**
 * PERFORMANCE_AUDIT §5.1 (S1): which frame a signed-in page gets, decided once from the URL, the course layout's area
 * declaration and the cached `/me/lms` answer. Dependency-free (structural types only) so `shellKind.check.ts` runs it
 * with plain `tsc` + `node`.
 *
 * - `player`: the attempt player, no chrome at all;
 * - `app`: the `AppHeader` frame (teachers, organization admins, platform admins, guardians on their areas);
 * - `student`: the sidebar + tab bar frame (the Learning area);
 * - `neutral`: a loading frame (brand bar + skeleton) used only while nothing decides yet.
 */
import { courseIdOfPath } from "./studentNav";

export type ShellKind = "student" | "app" | "player" | "neutral";
/** Same union as `AreaKey` in `components/ui/AppHeader.tsx` (kept here so this file has no component imports). */
export type ShellArea = "learning" | "teaching" | "organization" | "platform" | "parent";

/** The only `MeOut` fields that decide the frame. */
export interface ShellMe {
  is_teacher: boolean;
  can_create_courses: boolean;
  is_platform_admin: boolean;
  has_student_enrollments?: boolean;
}

// SF-1 (STUDENT_UI_FIX_PLAN §2.1): the player route (exact path) has no chrome at all
const PLAYER_ROUTE = /^\/courses\/[^/]+\/attempts\/[^/]+$/;
/** The attempt player, `/courses/{c}/attempts/{id}` (path without the language prefix). */
export const isPlayerRoute = (rest: string) => PLAYER_ROUTE.test(rest);

/** Teaches, creates courses or runs the platform: such a person's course pages wait for the course's own area. */
export function teaches(me: ShellMe): boolean {
  return !!(me.is_teacher || me.can_create_courses || me.is_platform_admin);
}

/** The tab `/courses` opens with (Teaching for people who teach or create courses), the same rule as the page. */
export function coursesDefault(me: ShellMe | null): ShellArea {
  return me && (me.is_teacher || me.is_platform_admin) && (me.is_teacher || me.can_create_courses) ? "teaching" : "learning";
}

/** Owner feedback 2026-11-08 (item 2): people who teach see Learning only once they learn somewhere. */
export function hidesLearning(me: ShellMe | null): boolean {
  return !!me && (me.is_teacher || me.can_create_courses) && me.has_student_enrollments === false;
}

/**
 * Area of a URL. `/courses` follows `?view=`; without it, `coursesDefault` (the tab `/courses` opens with:
 * Teaching for people who teach or create courses). Phase 6b S11b (UX 15).
 */
export function areaFromUrl(rest: string, view: string | null, coursesDefault: ShellArea = "learning"): ShellArea {
  if (rest === "/admin" || rest.startsWith("/admin/")) return "platform";
  if (rest === "/org" || rest.startsWith("/org/")) return "organization";
  if (rest === "/parent" || rest.startsWith("/parent/")) return "parent"; // Phase 11
  if (rest.startsWith("/grading-schemes") || rest === "/courses/new" || rest === "/courses/trash") return "teaching";
  if (rest.startsWith("/exam-templates")) return "teaching"; // Phase 7b S4
  if (rest === "/courses") {
    if (view === "teaching" || view === "learning") return view;
    return coursesDefault;
  }
  return "learning";
}

/** The URL's area for this person: without Learning, `/courses` (any `?view=`) is Teaching. */
export function urlAreaFor(rest: string, view: string | null, me: ShellMe | null): ShellArea {
  return hidesLearning(me) && rest === "/courses" ? "teaching" : areaFromUrl(rest, view, coursesDefault(me));
}

export interface ShellKindInput {
  /** Path without the language prefix. */
  rest: string;
  /** `?view=` of the URL. */
  view: string | null;
  /** The area a page declared (the course layout: `teaching` for its staff, `learning` for its students), or null. */
  declared: ShellArea | null;
  /** The cached or fresh `/me/lms` answer, null while nothing is known. */
  me: ShellMe | null;
}

export function shellKindFor({ rest, view, declared, me }: ShellKindInput): ShellKind {
  if (isPlayerRoute(rest)) return "player";
  // URLs of the other areas are the app frame for everyone: no answer is needed to know it
  if (areaFromUrl(rest, view) !== "learning") return "app";
  if (!me) return "neutral";
  if (urlAreaFor(rest, view, me) !== "learning") return "app";
  if (declared && declared !== "learning") return "app";
  // a course page of someone who teaches: the course's own declaration decides (a course they teach is Teaching)
  if (!declared && courseIdOfPath(rest) && teaches(me)) return "neutral";
  return "student";
}
