"use client";

// Phase 10 S6: course analytics (tabs Overview and Quizzes). Staff and org admins; aggregates only.
import React, { useCallback, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import {
  getCourseAnalytics, listAssignmentAnalytics, listModuleAnalytics, listQuizAnalytics,
  type AssignmentRowOut, type ModuleRowOut, type QuizRollupRowOut,
} from "@/lib/lms/analytics";
import { useCourse } from "@/components/lms/CourseContext";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { PageHeader, StatTile, Table, TabPanel, Tabs, type TableColumn } from "@/components/ui";
import { Loaded, ScoreAndSubmissions, pct, useLoaded } from "./parts";

export function CourseAnalytics() {
  const { t } = useTranslation();
  const { course } = useCourse();
  const [tab, setTab] = useState("overview");
  return (
    <div>
      <PageHeader title={t("analytics.title")} />
      <Tabs id="an" label={t("analytics.title")} value={tab} onChange={setTab}
        items={[{ id: "overview", label: t("analytics.tabs.overview") }, { id: "quizzes", label: t("analytics.tabs.quizzes") }]} />
      <TabPanel tabsId="an" value="overview" hidden={tab !== "overview"}>{tab === "overview" && <Overview courseId={course.id} />}</TabPanel>
      <TabPanel tabsId="an" value="quizzes" hidden={tab !== "quizzes"}>{tab === "quizzes" && <Quizzes courseId={course.id} />}</TabPanel>
    </div>
  );
}

function Overview({ courseId }: { courseId: string }) {
  const { t } = useTranslation();
  const q = useLoaded(() => getCourseAnalytics(courseId), [courseId]);
  const d = q.data;
  return (
    <Loaded {...q}>
      {d && (
        <>
          <ScoreAndSubmissions score={d.score} submissions={d.submissions} extra={<>
            <StatTile label={t("analytics.students")} value={d.students} />
            <StatTile label={t("analytics.completedAll")} value={d.completed_all} hint={t("analytics.ofModules", { n: d.modules_total })} />
          </>} />
          <Modules courseId={courseId} />
          <Assignments courseId={courseId} />
        </>
      )}
    </Loaded>
  );
}

function Modules({ courseId }: { courseId: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const list = useCursorList(useCallback((cursor: string | null) => listModuleAnalytics(courseId, { cursor }), [courseId]));
  const state = useTableState(list);
  const num = (key: string, label: string, get: (r: ModuleRowOut) => number): TableColumn<ModuleRowOut> =>
    ({ key, header: label, label, align: "right", nowrap: true, cell: get });
  const columns: TableColumn<ModuleRowOut>[] = [
    { key: "title", header: t("analytics.col.module"), primary: true, cell: (r) => pickLocalized(r.title, lang, course.default_language) },
    num("completed", t("analytics.col.completed"), (r) => r.completed),
    num("started", t("analytics.col.started"), (r) => r.started),
    num("unlocked", t("analytics.col.unlocked"), (r) => r.unlocked),
    num("locked", t("analytics.col.locked"), (r) => r.locked),
    num("not_started", t("analytics.col.notStarted"), (r) => r.not_started),
  ];
  return (
    <section className="mt-8">
      <h2 className="mb-2 text-base font-semibold text-slate-900">{t("analytics.modules")}</h2>
      <Table caption={t("analytics.modules")} columns={columns} rows={list.items} rowKey={(r) => r.module_id} {...state} />
      <MoreError list={list} />
    </section>
  );
}

function Assignments({ courseId }: { courseId: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const list = useCursorList(useCallback((cursor: string | null) => listAssignmentAnalytics(courseId, { cursor }), [courseId]));
  const state = useTableState(list);
  const num = (key: string, label: string, get: (r: AssignmentRowOut) => React.ReactNode): TableColumn<AssignmentRowOut> =>
    ({ key, header: label, label, align: "right", nowrap: true, cell: get });
  const columns: TableColumn<AssignmentRowOut>[] = [
    { key: "title", header: t("analytics.col.assignment"), primary: true, cell: (r) => pickLocalized(r.title, lang, course.default_language) },
    { key: "due", header: t("analytics.col.due"), label: t("analytics.col.due"), nowrap: true, cell: (r) => fmtShortDateTime(r.due_at, lang) || "—", hideInCard: (r) => !r.due_at },
    num("submitted", t("analytics.col.submitted"), (r) => `${r.submitted}/${r.students}`),
    num("graded", t("analytics.graded"), (r) => r.graded),
    num("pending", t("analytics.pendingReview"), (r) => r.pending_review),
    num("missing", t("analytics.missing"), (r) => r.missing),
    num("late", t("analytics.col.late"), (r) => r.late),
    num("mean", t("analytics.col.mean"), (r) => pct(r.mean_percent)),
  ];
  return (
    <section className="mt-8">
      <h2 className="mb-2 text-base font-semibold text-slate-900">{t("analytics.assignments")}</h2>
      <Table caption={t("analytics.assignments")} columns={columns} rows={list.items} rowKey={(r) => r.assignment_id} {...state} />
      <MoreError list={list} />
    </section>
  );
}

function Quizzes({ courseId }: { courseId: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const list = useCursorList(useCallback((cursor: string | null) => listQuizAnalytics(courseId, { cursor }), [courseId]));
  const state = useTableState(list);
  const columns: TableColumn<QuizRollupRowOut>[] = [
    {
      key: "title", header: t("analytics.col.quiz"), primary: true,
      cell: (r) => (
        <Link className="text-brand-700 underline-offset-2 hover:underline" href={`/${lang}/courses/${courseId}/analytics/quizzes/${r.assessment_id}`}>
          {pickLocalized(r.title, lang, course.default_language)}
        </Link>
      ),
    },
    { key: "attempts", header: t("analytics.col.attempts"), label: t("analytics.col.attempts"), align: "right", nowrap: true, cell: (r) => r.attempts },
    { key: "students", header: t("analytics.students"), label: t("analytics.students"), align: "right", nowrap: true, cell: (r) => r.students },
    { key: "mean", header: t("analytics.col.mean"), label: t("analytics.col.mean"), align: "right", nowrap: true, cell: (r) => pct(r.mean_percent) },
  ];
  return (
    <>
      <Table caption={t("analytics.tabs.quizzes")} columns={columns} rows={list.items} rowKey={(r) => r.assessment_id} {...state} />
      <MoreError list={list} />
    </>
  );
}
