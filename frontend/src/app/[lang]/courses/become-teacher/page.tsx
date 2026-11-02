import { redirect } from "next/navigation";

/** Old route (Phase 1): the application is on the public page. */
export default async function BecomeTeacherRedirect({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  redirect(`/${lang}/for-teachers/apply`);
}
