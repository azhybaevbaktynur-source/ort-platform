"use client";

// Phase 6b S6b: the course catalog on its own page (/courses/catalog; was a block above "My courses", UX S3).
// UX S11: the student count only from 10 up (an empty course does not look dead); language names, not codes.
import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, LayoutGrid, Users } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { isActiveMember, joinOpenCourse, listCatalog, type CatalogCourseOut } from "@/lib/lms/catalog";
import { pickLocalized } from "@/lib/lms/localized";
import { Button, EmptyState, ErrorState, LinkButton, PageHeader, Pagination, Skeleton } from "@/components/ui";
import { useErrorText } from "./useErrorText";

const SHOW_COUNT_FROM = 10;

function CatalogSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">{t("ui.loading")}</span>
      <div aria-hidden="true" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
            <Skeleton className="mb-3 h-5 w-2/3" />
            <Skeleton className="mb-2 h-4 w-full" />
            <Skeleton className="mb-4 h-4 w-1/2" />
            <Skeleton className="h-11 w-full rounded-xl" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function CatalogView() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const errorText = useErrorText();
  const [items, setItems] = useState<CatalogCourseOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [joining, setJoining] = useState<string | null>(null);
  const [joinError, setJoinError] = useState<{ id: string; error: unknown } | null>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listCatalog(next);
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const join = async (course: CatalogCourseOut) => {
    setJoining(course.id);
    setJoinError(null);
    try {
      const res = await joinOpenCourse(course.id);
      router.push(`/${lang}/courses/${res.course.id}`);
    } catch (e) {
      setJoinError({ id: course.id, error: e });
      setJoining(null);
    }
  };

  const action = (c: CatalogCourseOut) => {
    if (isActiveMember(c)) {
      return <LinkButton variant="secondary" fullWidth href={`/${lang}/courses/${c.id}`}>{t("catalog.open")}</LinkButton>;
    }
    if (c.enrollment_mode === "open") {
      return (
        <Button variant="secondary" fullWidth loading={joining === c.id} disabled={joining !== null && joining !== c.id} onClick={() => void join(c)}>
          {t("catalog.join")}
        </Button>
      );
    }
    return (
      <p className="text-sm leading-6 text-slate-600">
        {c.enrollment_mode === "invite_code" ? t("catalog.needsCode") : t("catalog.closed")}
      </p>
    );
  };

  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader title={t("catalog.title")} description={t("catalog.subtitle")}
        breadcrumbs={[{ label: t("lms.nav.myCourses"), href: `/${lang}/courses` }, { label: t("catalog.title") }]}
        secondaryActions={<LinkButton variant="secondary" href={`/${lang}/courses/join`} leftIcon={<KeyRound className="h-4 w-4" aria-hidden="true" />}>{t("home.primary.join")}</LinkButton>} />

      {error && items.length === 0 ? <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} /> : null}
      {error && items.length > 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} className="mb-4" /> : null}
      {loading && items.length === 0 && !error && <CatalogSkeleton />}
      {!loading && !error && items.length === 0 && (
        <EmptyState icon={<LayoutGrid />} title={t("home.catalogEmpty.title")} description={t("home.catalogEmpty.body")}
          action={<LinkButton href={`/${lang}/courses/join`}>{t("home.primary.join")}</LinkButton>} />
      )}
      {items.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((c) => {
            const title = pickLocalized(c.title, lang, c.default_language) || t("courses.list.untitled");
            const description = pickLocalized(c.description, lang, c.default_language);
            return (
              <li key={c.id} className="flex flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
                <h2 className="break-words text-lg font-semibold leading-7 text-slate-900">{title}</h2>
                {description && <p className="mt-1 line-clamp-3 text-base leading-6 text-slate-600 sm:text-sm">{description}</p>}
                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm leading-6 text-slate-600">
                  <span>{c.languages.map((l) => t(`courses.languages.${l}`)).join(", ")}</span>
                  {c.student_count >= SHOW_COUNT_FROM && (
                    <span className="inline-flex items-center gap-1">
                      <Users className="h-4 w-4" aria-hidden="true" />
                      {t("catalog.students", { count: c.student_count })}
                    </span>
                  )}
                </div>
                <div className="mt-auto pt-4">{action(c)}</div>
                {joinError?.id === c.id && <ErrorState variant="inline" message={errorText(joinError.error)} className="mt-3" />}
              </li>
            );
          })}
        </ul>
      )}
      <Pagination nextCursor={cursor} loading={loading} onLoadMore={() => void load(cursor)} />
    </div>
  );
}
