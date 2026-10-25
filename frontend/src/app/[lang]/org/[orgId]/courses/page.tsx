"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listOrgCourses, type OrgCourseOut } from "@/lib/lms/organizations";
import { useOrg } from "@/components/lms/org/OrgShell";
import { OrgCourseList } from "@/components/lms/org/OrgCourseList";
import { EmptyBox, Loading, OrgError, btn, inputCls, labelCls } from "@/components/lms/org/OrgUi";
import { Pager } from "@/components/lms/Pager";

export default function OrgCoursesPage() {
  const { lang, t } = useTranslation();
  const { org, readOnly } = useOrg();
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [items, setItems] = useState<OrgCourseOut[]>([]);
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
      const page = await listOrgCourses(org.id, { cursor: next });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [org.id]);
  useEffect(() => { void load(); }, [load]);
  // The courses endpoint has no text filter: search the loaded rows (any title language, owner).
  const needle = q.toLowerCase();
  const shown = needle
    ? items.filter((c) => [...Object.values(c.title), c.owner.display_name ?? "", c.owner.email]
      .some((v) => (v ?? "").toLowerCase().includes(needle)))
    : items;

  const base = `/${lang}/org/${org.id}/courses`;
  const create = readOnly ? (
    <button type="button" className={btn.primary} disabled><Plus className="h-4 w-4" aria-hidden="true" />{t("organizations.courses.create")}</button>
  ) : (
    <Link href={`${base}/new`} className={btn.primary}><Plus className="h-4 w-4" aria-hidden="true" />{t("organizations.courses.create")}</Link>
  );
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold text-slate-900">{t("organizations.courses.title")}</h2>
        {create}
      </div>
      <div className="mb-3 w-full sm:w-72">
        <label htmlFor="c-q" className={labelCls}>{t("lms.common.search")}</label>
        <input id="c-q" value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("organizations.courses.searchPlaceholder")} className={inputCls} />
      </div>
      {error ? <OrgError error={error} onRetry={() => load()} className="mb-3" /> : null}
      {loading && items.length === 0 && !error && <Loading />}
      {!loading && !error && shown.length === 0 && (
        <EmptyBox text={q ? t("organizations.courses.emptySearch") : t("organizations.courses.empty")}>{!q && !readOnly ? create : null}</EmptyBox>
      )}
      {shown.length > 0 && (
        <>
          <p className="mb-2 text-xs text-slate-500">{t("organizations.courses.shown", { n: shown.length })}</p>
          <OrgCourseList courses={shown} hrefFor={(c) => `${base}/${c.id}`} />
        </>
      )}
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
    </div>
  );
}
