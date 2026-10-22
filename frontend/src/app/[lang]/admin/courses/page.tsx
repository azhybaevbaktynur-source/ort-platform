"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { listAdminCourses } from "@/lib/lms/admin";
import type { AdminCourseOut } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Pager } from "@/components/lms/Pager";

export default function AdminCoursesPage() {
  const { lang, t } = useTranslation();
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [deleted, setDeleted] = useState(false);
  const [items, setItems] = useState<AdminCourseOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    const h = setTimeout(() => setQ(input.trim()), 350);
    return () => clearTimeout(h);
  }, [input]);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listAdminCourses({ q, deleted: deleted ? true : undefined, cursor: next });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [q, deleted]);
  useEffect(() => { void load(); }, [load]);

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold text-slate-900">{t("platformAdmin.courses.title")}</h1>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="c-q" className="block text-xs font-medium text-slate-600">{t("lms.common.search")}</label>
          <input id="c-q" value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("platformAdmin.courses.searchPlaceholder")}
            className="w-64 rounded-xl border border-slate-300 px-3 py-2 text-sm" />
        </div>
        <label className="flex items-center gap-2 pb-2 text-sm text-slate-700">
          <input type="checkbox" checked={deleted} onChange={(e) => setDeleted(e.target.checked)} />
          {t("platformAdmin.courses.deletedOnly")}
        </label>
      </div>
      {error ? <ErrorMessage error={error} onRetry={() => load()} className="mb-4" /> : null}
      {loading && items.length === 0 && !error && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{t("platformAdmin.courses.empty")}</p>
      )}
      {items.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2">{t("platformAdmin.courses.course")}</th>
                <th className="px-3 py-2">{t("platformAdmin.courses.owner")}</th>
                <th className="px-3 py-2">{t("platformAdmin.courses.status")}</th>
                <th className="px-3 py-2">{t("platformAdmin.courses.students")}</th>
                <th className="px-3 py-2">{t("platformAdmin.courses.flags")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((c) => (
                <tr key={c.id}>
                  <td className="px-3 py-2"><Link href={`/${lang}/admin/courses/${c.id}`} className="font-medium text-brand-700 hover:underline">{pickLocalized(c.title, lang, "en") || c.id}</Link></td>
                  <td className="px-3 py-2">{c.owner.display_name || c.owner.email}</td>
                  <td className="px-3 py-2">{t(`courses.status.${c.status}`)}</td>
                  <td className="px-3 py-2">{c.active_student_count}</td>
                  <td className="space-x-1 px-3 py-2 text-xs">
                    {c.deleted_at && <span className="rounded-full bg-red-100 px-2 py-0.5 font-semibold text-red-800">{t("platformAdmin.courses.deleted")}</span>}
                    {c.unlisted_by_admin_at && <span className="rounded-full bg-amber-100 px-2 py-0.5 font-semibold text-amber-800">{t("platformAdmin.courses.unlisted")}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
    </div>
  );
}
