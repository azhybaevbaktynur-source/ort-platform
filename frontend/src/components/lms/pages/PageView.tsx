"use client";

// Phase 8a S4b: page viewer (design 8.1). `body_html` is sanitized by the server and typeset with KaTeX in SafeHtml.
// Reused by the course home when `home_kind = page` (`embedded` drops the breadcrumbs). A 423 shows the locked state.
// Phase 8c S3 (PHASE_8C_DESIGN §5.2): the Preview tab of the page object (`preview`: the saved page as students see
// it, no Edit button; the language chips stay in the Preview tab of the variant).
import React, { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Pencil } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { getPage } from "@/lib/lms/pages";
import { isStaffPage, type PageAnyOut } from "@/lib/lms/pagesTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { Badge, LinkButton, LoadingState, PageHeader } from "@/components/ui";
import { ContentError, LockedState, isModuleLocked } from "./ApiError";
import { SafeHtml } from "./SafeHtml";
import { LangChip } from "./LangChip";

export function PageView({ pageId, embedded = false, preview = null }: {
  pageId: string;
  embedded?: boolean;
  /** Phase 8c S3: inside the page object's Preview tab; `variantHref` is the link of a language variant. */
  preview?: { variantHref: (id: string) => string } | null;
}) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const fromModule = useSearchParams()?.get("from") === "module"; // 8a UX M7: set by module item links
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
        breadcrumbs={embedded || preview || !staffRole ? undefined : [{ label: t("pages.title"), href: `${base}/pages` }, { label: page.title }]}
        badge={staff && !staff.published ? <Badge tone="neutral">{t("pages.draft")}</Badge> : undefined}
        primaryAction={staffRole && !preview ? (
          <LinkButton href={`${base}/pages/${page.id}?tab=edit`} leftIcon={<Pencil className="h-4 w-4" aria-hidden="true" />}>{t("pages.view.edit")}</LinkButton>
        ) : undefined}
      >
        {page.variants.length > 0 && (
          <nav aria-label={t("pages.view.variants")} className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-sm text-slate-600">{t("pages.view.variants")}</span>
            <LangChip label={t(`pages.lang.${page.language}`)} selected />
            {page.variants.map((v) => (
              <LangChip key={v.id} label={t(`pages.lang.${v.language}`)} href={preview ? preview.variantHref(v.id) : `${base}/pages/${v.id}${fromModule ? "?from=module" : ""}`} />
            ))}
          </nav>
        )}
      </PageHeader>
      <SafeHtml html={page.body_html} />
      <p className="mt-6 text-xs text-slate-600">{t("pages.view.updated", { date: fmtShortDateTime(page.updated_at, lang) })}</p>
      {/* 8a UX M7: a page opened from a module offers the way back as the next step */}
      {fromModule && !embedded && !preview && (
        <div className="mt-6 [&>*]:w-full sm:[&>*]:w-auto">
          <LinkButton variant="secondary" href={`${base}/modules`} leftIcon={<ArrowLeft aria-hidden="true" className="h-4 w-4" />}>
            {t("pages.locked.toModules")}
          </LinkButton>
        </div>
      )}
    </article>
  );
}
