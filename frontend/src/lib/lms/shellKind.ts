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

/**
 * Owner decision 2026-11-12 (fix round 1e): student and teacher are separate accounts. A person who teaches never gets
 * the Learning area, whatever student enrolments they still have (the data stays; the UI ignores it); they check their
 * courses through Student view. The backend's `learns_here` (`home/bootstrap.py`) is the same rule.
 */
export function hidesLearning(me: ShellMe | null): boolean {
  return !!me && teaches(me);
}

/** Owner decision 2026-11-12 (fix round 1b): the person learns here (gets the Learning area, the student frame and Pro). */
export function learnsHere(me: ShellMe): boolean {
  return !teaches(me);
}

/** Where a person who has no Learning area lives: Teaching for people who teach or create courses, else Platform. */
export function homeArea(me: ShellMe): ShellArea {
  if (me.is_teacher || me.can_create_courses) return "teaching";
  return me.is_platform_admin ? "platform" : "learning";
}

/**
 * Area of a URL. Step 3a S3 (STUDENT_IA_DESIGN §2.1): `/home`, `/courses` and `/courses/choose` claim no staff area
 * (`?view=` is gone), so for people who learn they are Learning and for people who teach `urlAreaFor` gives their home
 * area (`/courses` is the Teaching list, `/home` lands there too). S7 (v3): for a learner `/courses` and
 * `/courses/choose` are only redirects (to `/home` and to the catalog), drawn inside the student frame.
 */
export function areaFromUrl(rest: string): ShellArea {
  if (rest === "/admin" || rest.startsWith("/admin/")) return "platform";
  if (rest === "/org" || rest.startsWith("/org/")) return "organization";
  if (rest === "/parent" || rest.startsWith("/parent/")) return "parent"; // Phase 11
  if (rest.startsWith("/grading-schemes") || rest === "/courses/new" || rest === "/courses/trash") return "teaching";
  if (rest.startsWith("/exam-templates")) return "teaching"; // Phase 7b S4
  return "learning";
}

/**
 * The URL's area for this person. Fix round 1b (Better idea 4): a URL no staff area claims (`/home`, `/courses`, `/pro`,
 * `/privacy`, the catalog, `/courses/join`, `/invitations`, course pages, anything new) is Learning only for people who
 * learn; people who teach or administer get their home area (`homeArea`) there.
 */
export function urlAreaFor(rest: string, me: ShellMe | null): ShellArea {
  const area = areaFromUrl(rest);
  return area === "learning" && me && hidesLearning(me) ? homeArea(me) : area;
}

/** The URL claims no area itself (only Learning would), so a page's own declaration may decide (course pages). */
export function pageDecidesArea(rest: string): boolean {
  return areaFromUrl(rest) === "learning";
}

/**
 * The header's active area: the URL's, or where the URL claims none, the page's declaration (a course page is
 * Teaching for its staff); a declared Learning never wins for people without Learning.
 */
export function activeAreaFor(rest: string, declared: ShellArea | null, me: ShellMe | null): ShellArea {
  const urlArea = urlAreaFor(rest, me);
  if (!declared || !pageDecidesArea(rest)) return urlArea;
  return declared === "learning" && hidesLearning(me) ? urlArea : declared;
}

export interface ShellKindInput {
  /** Path without the language prefix. */
  rest: string;
  /** The area a page declared (the course layout: `teaching` for its staff, `learning` for its students), or null. */
  declared: ShellArea | null;
  /** The cached or fresh `/me/lms` answer, null while nothing is known. */
  me: ShellMe | null;
}

export function shellKindFor({ rest, declared, me }: ShellKindInput): ShellKind {
  if (isPlayerRoute(rest)) return "player";
  // URLs of the other areas are the app frame for everyone: no answer is needed to know it
  if (areaFromUrl(rest) !== "learning") return "app";
  if (!me) return "neutral";
  // Fix round 1b (owner decision 2026-11-12, Better idea 4): the frame comes from the person, not the URL. People who
  // teach or administer never get the student frame (not on /pro, the catalog, a course they once joined as a student
  // or a course they do not teach); their course pages need no declaration to know it, so they never wait for one
  if (!learnsHere(me)) return "app";
  if (urlAreaFor(rest, me) !== "learning") return "app";
  if (declared && declared !== "learning") return "app";
  return "student";
}
