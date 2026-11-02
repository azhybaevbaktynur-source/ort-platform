import { redirect } from "next/navigation";

/** Old route: the application is on the public page; invitations have their own page (`/invitations`). */
export default async function TeacherAccessRedirect({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  redirect(`/${lang}/for-teachers/apply`);
}
