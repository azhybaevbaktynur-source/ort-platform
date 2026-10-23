"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Users } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { isActiveMember, joinOpenCourse, listCatalog, type CatalogCourseOut } from "@/lib/lms/catalog";
import { pickLocalized } from "@/lib/lms/localized";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Pager } from "@/components/lms/Pager";

/** Phase 5 S3: catalog block on /[lang]/courses (anchor #catalog). Hidden while the catalog is empty. */
export function CatalogSection({ onJoined }: { onJoined?: (courseId: string) => void }) {
  const { lang, t } = useTranslation();
  const [items, setItems] = useState<CatalogCourseOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [joining, setJoining] = useState<string | null>(null);

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

  useEffect(() => {
    void load();
  }, [load]);

  const join = async (course: CatalogCourseOut) => {
    setJoining(course.id);
    setError(null);
    try {
      const res = await joinOpenCourse(course.id);
      setItems((prev) => prev.map((c) => (c.id === course.id ? {
        ...c,
        my_enrollment: { role: res.enrollment.role, state: res.enrollment.state },
        student_count: c.student_count + (res.already_enrolled || res.enrollment.role !== "student" ? 0 : 1),
      } : c)));
      onJoined?.(course.id);
    } catch (e) {
      setError(e);
    } finally {
      setJoining(null);
    }
  };

  if (!loading && !error && items.length === 0) return null;

  const action = (c: CatalogCourseOut) => {
    if (isActiveMember(c)) {
      return (
        <Link href={`/${lang}/courses/${c.id}`}
          className="inline-flex items-center rounded-xl border border-brand-600 px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-50">
          {t("catalog.open")}
        </Link>
      );
    }
    if (c.enrollment_mode === "open") {
      return (
        <button type="button" disabled={joining !== null} onClick={() => void join(c)}
          className="inline-flex items-center rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">
          {joining === c.id ? t("catalog.joining") : t("catalog.join")}
        </button>
      );
    }
    return (
      <span className="text-xs text-slate-500">
        {c.enrollment_mode === "invite_code" ? t("catalog.needsCode") : t("catalog.closed")}
      </span>
    );
  };

  return (
    <section id="catalog" aria-labelledby="catalog-title" className="mb-8">
      <h2 id="catalog-title" className="text-lg font-bold text-slate-900">{t("catalog.title")}</h2>
      <p className="mb-4 text-sm text-slate-500">{t("catalog.subtitle")}</p>
      {error ? <ErrorMessage error={error} onRetry={() => void load()} className="mb-4" /> : null}
      {loading && items.length === 0 && !error && (
        <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((c) => {
          const title = pickLocalized(c.title, lang, c.default_language) || t("courses.list.untitled");
          const description = pickLocalized(c.description, lang, c.default_language);
          return (
            <article key={c.id} className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="line-clamp-2 text-base font-bold text-slate-900">{title}</h3>
              {description && <p className="mt-1 line-clamp-3 text-sm text-slate-600">{description}</p>}
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
                <span>{c.languages.map((l) => l.toUpperCase()).join(" / ")}</span>
                <span className="inline-flex items-center gap-1">
                  <Users className="h-3.5 w-3.5" aria-hidden="true" />
                  {t("catalog.students", { count: c.student_count })}
                </span>
              </div>
              <div className="mt-4">{action(c)}</div>
            </article>
          );
        })}
      </div>
      <Pager nextCursor={cursor} loading={loading} onMore={() => void load(cursor)} />
    </section>
  );
}
