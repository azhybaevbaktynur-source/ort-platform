/**
 * The hero's role entries. `href` follows `/{lang}`; the label is `landing.hero.roles.<key>` in en, ky and ru.
 * "I'm a parent" later is one line here plus that key.
 */
export const ROLE_ENTRIES: readonly { key: string; href: string }[] = [
  { key: "student", href: "/register" },
  { key: "teacher", href: "/for-teachers" },
];

/** Full-width bands keep their content in this column, so 1920 px does not look empty. */
export const LANDING_INNER = "mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-8";
