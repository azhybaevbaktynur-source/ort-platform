"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useCourse } from "@/components/lms/CourseContext";
import { MistakesList } from "@/components/lms/progress/MistakesList";
import { AnalyticsOverview, PeriodPicker } from "@/components/lms/progress/AnalyticsOverview";
import { TabPanel, Tabs } from "@/components/ui";
import { StudentPageHeader } from "@/components/lms/student/StudentPageHeader";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { templateUi } from "@/lib/lms/templates";
import type { ActivityDays } from "@/lib/lms/progress";

type Tab = "overview" | "mistakes";

function ProgressTabs() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  // exam-prep courses: the course layout drops its header here, so the course name is the subtitle
  const examPrep = templateUi(course).studentLayout === "exam_prep";
  const params = useSearchParams();
  const fromUrl: Tab = params.get("tab") === "mistakes" ? "mistakes" : "overview";
  const [tab, setTab] = useState<Tab>(fromUrl);
  const [period, setPeriod] = useState<ActivityDays>(30);
  // Student UI U2: the shell's "Аналитика" and "Мои ошибки" links change only `?tab=` on this same page
  useEffect(() => { setTab(fromUrl); }, [fromUrl]);
  const id = "progress-tabs";
  return (
    <div className="space-y-4">
      <StudentPageHeader title={t("progress.analytics.title")} className="mb-2"
        subtitle={examPrep ? pickLocalized(course.title, lang, course.default_language) : undefined}
        action={tab === "overview" ? <PeriodPicker value={period} onChange={setPeriod} /> : undefined} />
      <Tabs id={id} label={t("progress.tabsLabel")} value={tab} onChange={(v) => setTab(v as Tab)}
        items={[{ id: "overview", label: t("progress.tabs.overview") }, { id: "mistakes", label: t("progress.tabs.mistakes") }]} />
      <TabPanel tabsId={id} value="overview" hidden={tab !== "overview"}>
        {tab === "overview" && <AnalyticsOverview courseId={course.id} period={period} examPrep={examPrep} />}
      </TabPanel>
      <TabPanel tabsId={id} value="mistakes" hidden={tab !== "mistakes"}>
        {tab === "mistakes" && <MistakesList courseId={course.id} />}
      </TabPanel>
    </div>
  );
}

/** Student analytics (Student UI U6, §3.3) and the mistakes notebook (`?tab=mistakes`). The server answers 404 for staff. */
export default function ProgressPage() {
  return (
    <Suspense fallback={null}>
      <ProgressTabs />
    </Suspense>
  );
}
