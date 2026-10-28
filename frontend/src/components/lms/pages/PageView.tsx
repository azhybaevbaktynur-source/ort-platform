"use client";

// Phase 8a S4b: page viewer (design 8.1). `body_html` is sanitized by the server and typeset with KaTeX in SafeHtml.
// Reused by the course home when `home_kind = page` (`embedded` drops the breadcrumbs). A 423 shows the locked state.
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Pencil } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { getPage } from "@/lib/lms/pages";
import { isStaffPage, type PageAnyOut } from "@/lib/lms/pagesTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { Badge, LinkButton, LoadingState, PageHeader } from "@/components/ui";
import { ContentError, LockedState, isModuleLocked } from "./ApiError";
import { SafeHtml } from "./SafeHtml";

export function PageView({ pageId, embedded = false }: { pageId: string; embedded?: boolean }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const base = `/${lang}/courses/${course.id}`;
  const [page, setPage] = useState<PageAnyOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setLoading(true); setError(null);
    getPage(course.id, pageId)
      .then((p) => { if (live) setPage(p); })
      .catch((e) => { if (live) setError(e); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [course.id, pageId]);

  if (loading) return <LoadingState />;
  if (error) return isModuleLocked(error) ? <LockedState error={error} courseId={course.id} /> : <ContentError error={error} />;
  if (!page) return null;

  const staff = isStaffPage(page) ? page : null;
  const staffRole = canEdit && !!staff;
  return (
    <article className="max-w-3xl">
      <PageHeader
        title={page.title}
        breadcrumbs={embedded || !staffRole ? undefined : [{ label: t("pages.title"), href: `${base}/pages` }, { label: page.title }]}
        badge={staff && !staff.published ? <Badge tone="neutral">{t("pages.draft")}</Badge> : undefined}
        primaryAction={staffRole ? (
          <LinkButton href={`${base}/pages/${page.id}/edit`} leftIcon={<Pencil className="h-4 w-4" aria-hidden="true" />}>{t("pages.view.edit")}</LinkButton>
        ) : undefined}
      >
        {page.variants.length > 0 && (
          <nav aria-label={t("pages.view.variants")} className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-sm text-slate-600">{t("pages.view.variants")}</span>
            <Badge tone="info">{t(`pages.lang.${page.language}`)}</Badge>
            {page.variants.map((v) => (
              <Link key={v.id} href={`${base}/pages/${v.id}`} className="inline-flex min-h-11 items-center rounded-full border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 hover:bg-slate-50">
                {t(`pages.lang.${v.language}`)}
              </Link>
            ))}
          </nav>
        )}
      </PageHeader>
      <SafeHtml html={page.body_html} />
      <p className="mt-6 text-xs text-slate-600">{t("pages.view.updated", { date: fmtShortDateTime(page.updated_at, lang) })}</p>
    </article>
  );
}
