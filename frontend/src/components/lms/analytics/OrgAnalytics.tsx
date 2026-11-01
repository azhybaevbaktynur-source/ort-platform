"use client";

// Phase 10 S6: organization analytics (org admins; aggregates only, no question text, no per-student rows).
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import {
  getOrgAnalytics, listOrgCourseAnalytics, listOrgQuizAnalytics, type OrgCourseRowOut, type OrgQuizRollupRowOut,
} from "@/lib/lms/analytics";
import { listDepartments, type DepartmentOut } from "@/lib/lms/organizations";
import { useOrg } from "@/components/lms/org/OrgShell";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { PageHeader, Select, StatTile, Table, type TableColumn } from "@/components/ui";
import { Loaded, ScoreAndSubmissions, pct, useLoaded } from "./parts";

export function OrgAnalytics() {
  const { t } = useTranslation();
  const { org, crumbs } = useOrg();
  const q = useLoaded(() => getOrgAnalytics(org.id), [org.id]);
  const d = q.data;
  return (
    <div>
      <PageHeader title={t("analytics.title")} breadcrumbs={crumbs({ label: t("analytics.nav") })} />
      <Loaded {...q}>
        {d && (
          <>
            <ScoreAndSubmissions score={d.score} submissions={d.submissions} extra={<>
              <StatTile label={t("analytics.courses")} value={d.courses} />
              <StatTile label={t("analytics.students")} value={d.students} />
            </>} />
            <Courses orgId={org.id} />
            <Quizzes orgId={org.id} />
          </>
        )}
      </Loaded>
    </div>
  );
}

function Courses({ orgId }: { orgId: string }) {
  const { lang, t } = useTranslation();
  const [dept, setDept] = useState("");
  const [depts, setDepts] = useState<DepartmentOut[]>([]);
  useEffect(() => { listDepartments(orgId).then(setDepts).catch(() => setDepts([])); }, [orgId]);
  const fetchPage = useCallback((cursor: string | null) => listOrgCourseAnalytics(orgId, { cursor, department_id: dept || undefined }), [orgId, dept]);
  const list = useCursorList(fetchPage);
  const state = useTableState(list);
  const right = (key: string, label: string, get: (r: OrgCourseRowOut) => React.ReactNode): TableColumn<OrgCourseRowOut> =>
    ({ key, header: label, label, align: "right", nowrap: true, cell: get });
  const columns: TableColumn<OrgCourseRowOut>[] = [
    { key: "title", header: t("analytics.col.course"), primary: true, cell: (r) => pickLocalized(r.title, lang) },
    { key: "dept", header: t("analytics.col.department"), label: t("analytics.col.department"), cell: (r) => r.department_name },
    right("students", t("analytics.students"), (r) => r.students),
    right("completed", t("analytics.completedAll"), (r) => r.completed_all),
    right("mean", t("analytics.col.mean"), (r) => pct(r.mean_percent)),
    right("submitted", t("analytics.col.submittedCount"), (r) => r.submitted),
    right("missing", t("analytics.missing"), (r) => r.missing),
  ];
  const filter = depts.length > 1 ? (
    <Select label={t("analytics.col.department")} value={dept} onChange={(e) => setDept(e.target.value)} containerClassName="sm:max-w-xs"
      options={depts.map((x) => ({ value: x.id, label: x.name }))} placeholder={t("analytics.allDepartments")} />
  ) : undefined;
  return (
    <section className="mt-8">
      <h2 className="mb-2 text-base font-semibold text-slate-900">{t("analytics.courses")}</h2>
      <Table caption={t("analytics.courses")} columns={columns} rows={list.items} rowKey={(r) => r.course_id} search={filter} {...state} />
      <MoreError list={list} />
    </section>
  );
}

function Quizzes({ orgId }: { orgId: string }) {
  const { lang, t } = useTranslation();
  const list = useCursorList(useCallback((cursor: string | null) => listOrgQuizAnalytics(orgId, { cursor }), [orgId]));
  const state = useTableState(list);
  const columns: TableColumn<OrgQuizRollupRowOut>[] = [
    { key: "title", header: t("analytics.col.quiz"), primary: true, cell: (r) => pickLocalized(r.title, lang) },
    { key: "course", header: t("analytics.col.course"), label: t("analytics.col.course"), cell: (r) => pickLocalized(r.course_title, lang) },
    { key: "attempts", header: t("analytics.col.attempts"), label: t("analytics.col.attempts"), align: "right", nowrap: true, cell: (r) => r.attempts },
    { key: "students", header: t("analytics.students"), label: t("analytics.students"), align: "right", nowrap: true, cell: (r) => r.students },
    { key: "mean", header: t("analytics.col.mean"), label: t("analytics.col.mean"), align: "right", nowrap: true, cell: (r) => pct(r.mean_percent) },
  ];
  return (
    <section className="mt-8">
      <h2 className="mb-2 text-base font-semibold text-slate-900">{t("analytics.tabs.quizzes")}</h2>
      <Table caption={t("analytics.tabs.quizzes")} columns={columns} rows={list.items} rowKey={(r) => r.assessment_id} {...state} />
      <MoreError list={list} />
    </section>
  );
}
