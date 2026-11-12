"use client";

// Step 3b S3 (CATALOG_AND_TEACHERS_DESIGN 3.2): shared pieces of Admin → Преподаватели and the person page's
// «Преподавание» card. An independent teacher is «Независимый преподаватель», never an organization.
import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import type { TeacherRowOut } from "@/lib/lms/types";
import { fmtApiDate } from "@/lib/format";
import { isSystemAccount } from "@/lib/lms/organizations";
import { Card, DescriptionList } from "@/components/ui";

/** «Где преподаёт»: «Независимый преподаватель», the schools (at most 3, "+N"), or both. */
export function useWhereTeaches() {
  const { t } = useTranslation();
  return (r: TeacherRowOut) => {
    const more = r.school_count > r.schools.length ? ` ${t("platformAdmin.teachers.more", { n: r.school_count - r.schools.length })}` : "";
    const schools = r.schools.join(", ") + more;
    if (isSystemAccount(r.user)) return t("platformAdmin.catalog.platform"); // the owner of the platform's courses
    if (r.kind === "independent") return t("platformAdmin.teachers.independent");
    if (r.kind === "both") return `${t("platformAdmin.teachers.independentShort")} · ${schools}`;
    return schools;
  };
}

const linkCls = "inline-flex min-h-11 items-center font-medium text-brand-700 hover:underline sm:min-h-0";

/** The person page's «Преподавание» card: where the person teaches and since when, their courses, students and listed
 *  courses, with links to Admin → Курсы (their courses) and Admin → Каталог. Grant / revoke stay in the page header. */
export function TeachingCard({ teaching }: { teaching: TeacherRowOut }) {
  const { lang, t } = useTranslation();
  const since = teaching.since ? fmtApiDate(teaching.since, lang) : null;
  const system = isSystemAccount(teaching.user);
  const independent = teaching.kind !== "school" && !system;
  const items = [
    {
      key: "where", term: t("person.teaching.where"),
      description: (
        <span className="block space-y-1">
          {system && <span className="block">{t("platformAdmin.catalog.platform")}</span>}
          {independent && (
            <span className="block">{since ? t("person.teaching.independentSince", { date: since }) : t("platformAdmin.teachers.independent")}</span>
          )}
          {teaching.schools.length > 0 && (
            <span className="block break-words">
              {teaching.schools.join(", ")}
              {teaching.school_count > teaching.schools.length ? ` ${t("platformAdmin.teachers.more", { n: teaching.school_count - teaching.schools.length })}` : ""}
            </span>
          )}
        </span>
      ),
    },
    {
      key: "courses", term: t("person.teaching.courses"),
      description: (
        <span className="inline-flex flex-wrap items-center gap-x-3">
          {teaching.courses}
          {teaching.courses > 0 && <Link href={`/${lang}/admin/courses?owner_id=${encodeURIComponent(teaching.user.id)}`} className={linkCls}>{t("person.teaching.openCourses")}</Link>}
        </span>
      ),
    },
    { key: "students", term: t("person.teaching.students"), description: teaching.students },
    {
      key: "listed", term: t("person.teaching.listed"),
      description: (
        <span className="inline-flex flex-wrap items-center gap-x-3">
          {teaching.listed_courses}
          <Link href={`/${lang}/admin/catalog?state=listed`} className={linkCls}>{t("person.teaching.openCatalog")}</Link>
        </span>
      ),
    },
  ];
  return (
    <Card className="mb-6" title={t("person.teaching.title")} data-testid="teaching-card">
      <DescriptionList twoColumns items={items} />
    </Card>
  );
}
