import { redirect } from "next/navigation";

/** Step 3b S3 (CATALOG_AND_TEACHERS_DESIGN 3.2, owner D9): the teacher requests moved into Admin → Преподаватели, tab
 *  «Заявки». Old links and bookmarks keep working and keep their query (`?status=` picks the request filter). */
export default async function TeacherRequestsRedirect({ params, searchParams }: {
  params: Promise<{ lang: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { lang } = await params;
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(await searchParams)) {
    if (k === "tab") continue;
    for (const one of Array.isArray(v) ? v : v === undefined ? [] : [v]) query.append(k, one);
  }
  const rest = query.toString();
  redirect(`/${lang}/admin/teachers?tab=requests${rest ? `&${rest}` : ""}`);
}
