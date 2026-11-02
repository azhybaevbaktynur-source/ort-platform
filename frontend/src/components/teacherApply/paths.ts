/** The apply page, as the place to come back to after logging in. The entered form never goes in a URL. */
export function loginBackHref(lang: string): string {
  return `/${lang}/login?redirect=${encodeURIComponent(`/${lang}/for-teachers/apply`)}`;
}
