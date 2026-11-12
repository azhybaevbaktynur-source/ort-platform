/**
 * Step 3a S3: where «Выбрать курсы» / «Добавить курс» and «Продолжить» with no course lead. The choose step
 * (`/courses/choose`, STUDENT_IA_DESIGN §4) comes with S4; until then every such link opens the catalog, so S3 can
 * deploy alone without a dead link. S4 switches this one function to `/${lang}/courses/choose`. Dependency-free.
 */
export function chooseCoursesHref(lang: string): string {
  return `/${lang}/courses/catalog`;
}
