import { redirect } from "next/navigation";

/** Old route (S3 access): the Pro page replaced it (docs/phases/SUBSCRIPTION_DESIGN.md 6); links from e-mails keep
 *  working and keep their query. */
export default async function UnlockRedirect({ params, searchParams }: {
  params: Promise<{ lang: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { lang } = await params;
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(await searchParams)) {
    for (const one of Array.isArray(v) ? v : v === undefined ? [] : [v]) query.append(k, one);
  }
  const qs = query.toString();
  redirect(`/${lang}/pro${qs ? `?${qs}` : ""}`);
}
