/**
 * UX rework (UX_REWORK_DESIGN A): the one width of the signed-in app, used by the header bars and `<main>`.
 * Tailwind sees this file (`src/components/**`), so the class names may live in a constant.
 */
export const SHELL_WIDTH = "mx-auto w-full max-w-[1600px] px-4 sm:px-6 lg:px-8";

/**
 * Exception (PUR-6): `/courses/[id]/attempts/**` keep the column they had before the rework, to the pixel: the
 * outer box cancels the shell's padding from `sm` and the inner one is the old `max-w-6xl` with its `px-4` (phones
 * keep the shell's own `px-4`).
 */
export const EXAM_COLUMN_OUTER = "sm:-mx-6 lg:-mx-8";
export const EXAM_COLUMN_INNER = "mx-auto max-w-6xl sm:px-4";

/**
 * FB8 S0 (STAFF_UX_AUDIT §0): the column width of a staff page by its type, inside `SHELL_WIDTH`. `list` for tables and
 * lists, `form` for a form alone, `formPreview` for a 720 px form with a 360 px preview, `reading` for text. Callers add
 * `w-full` (and `mx-auto` if centred) themselves. Nothing but a table stretches to the shell's 1600 px.
 */
export const STAFF_WIDTH = {
  list: "max-w-[1200px]",
  form: "max-w-[720px]",
  formPreview: "max-w-[1120px]",
  reading: "max-w-3xl",
} as const;
export type StaffWidth = keyof typeof STAFF_WIDTH;
