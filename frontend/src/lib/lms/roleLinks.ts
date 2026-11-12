/**
 * Fix round 2026-11-12 1b: what every link should open, per role, as data. The per-role link check
 * (`e2e/role-links.spec.ts`) compares each landed page's `data-shell` / `data-area` (set by `LmsShell`) with
 * `expectedFrame` / `expectedArea`; `roleLinks.check.ts` pins the rules for a fixed URL table without a browser.
 * Dependency-free (only `shellKind.ts`): the same rules the shell uses, never a second copy of them.
 *
 * Owner decision 2026-11-12: teachers and students are separate accounts, so there is no teacher+student role;
 * `teacher_enrolled` is a teacher with a leftover student enrolment and must get exactly the teacher experience.
 */
import { activeAreaFor, learnsHere, shellKindFor, type ShellArea, type ShellKind, type ShellMe } from "./shellKind";

export type Role = "student" | "teacher" | "teacher_enrolled" | "org_admin" | "platform_admin";
export const ROLES: Role[] = ["student", "teacher", "teacher_enrolled", "org_admin", "platform_admin"];

/** The `/me/lms` answer of each e2e person (`e2e/seed_backend.py`), reduced to the fields that decide the frame. */
export const ROLE_ME: Record<Role, ShellMe> = {
  student: { is_teacher: false, can_create_courses: false, is_platform_admin: false, has_student_enrollments: true },
  teacher: { is_teacher: true, can_create_courses: true, is_platform_admin: false, has_student_enrollments: false },
  teacher_enrolled: { is_teacher: true, can_create_courses: true, is_platform_admin: false, has_student_enrollments: true },
  // the lyceum's org admin: an org_admin membership is teaching (`is_teacher`), and org admins create courses
  org_admin: { is_teacher: true, can_create_courses: true, is_platform_admin: false, has_student_enrollments: false },
  // platform admins are co-teachers of the ORT courses (P5-6)
  platform_admin: { is_teacher: true, can_create_courses: true, is_platform_admin: true, has_student_enrollments: false },
};

/** `rest` (path without origin and language prefix) and `?view=` of a link or a landed URL. */
export function splitPath(href: string): { rest: string; view: string | null } {
  const noOrigin = href.replace(/^[a-z]+:\/\/[^/]+/i, "");
  const [pathPart, query = ""] = noOrigin.split("#")[0].split("?");
  const rest = pathPart.replace(/^\/(en|ky|ru)(?=\/|$)/, "").replace(/\/+$/, "") || "/";
  const view = new URLSearchParams(query).get("view");
  return { rest, view };
}

/** The frame a fully loaded page of this URL must have for this role (never `neutral` once the account is known). */
export function expectedFrame(role: Role, href: string): ShellKind {
  const { rest, view } = splitPath(href);
  const me = ROLE_ME[role];
  // a learner's course page declares Learning; nobody else's declaration changes the frame
  return shellKindFor({ rest, view, declared: learnsHere(me) ? "learning" : null, me });
}

/** The header area a fully loaded page of this URL must highlight for this role. */
export function expectedArea(role: Role, href: string): ShellArea {
  const { rest, view } = splitPath(href);
  return activeAreaFor(rest, view, null, ROLE_ME[role]);
}

/** Pro in the account menu: only for people who learn. */
export const expectsPro = (role: Role): boolean => learnsHere(ROLE_ME[role]);
/** The Learning area («Учёба»): only for people who learn. */
export const expectsLearning = (role: Role): boolean => learnsHere(ROLE_ME[role]);
