"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useCourse } from "@/components/lms/CourseContext";
import { MistakesList } from "@/components/lms/progress/MistakesList";
import { ProgressOverview } from "@/components/lms/progress/ProgressOverview";
import { PageHeader, TabPanel, Tabs } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";

type Tab = "overview" | "mistakes";

function ProgressTabs() {
  const { t } = useTranslation();
  const { course } = useCourse();
  const params = useSearchParams();
  const fromUrl: Tab = params.get("tab") === "mistakes" ? "mistakes" : "overview";
  const [tab, setTab] = useState<Tab>(fromUrl);
  // Student UI U2: the shell's "Аналитика" and "Мои ошибки" links change only `?tab=` on this same page
  useEffect(() => { setTab(fromUrl); }, [fromUrl]);
  const id = "progress-tabs";
  return (
    <div className="space-y-4">
      <PageHeader title={t("progress.title")} />
      <Tabs id={id} label={t("progress.tabsLabel")} value={tab} onChange={(v) => setTab(v as Tab)}
        items={[{ id: "overview", label: t("progress.tabs.overview") }, { id: "mistakes", label: t("progress.tabs.mistakes") }]} />
      <TabPanel tabsId={id} value="overview" hidden={tab !== "overview"}>
        {tab === "overview" && <ProgressOverview courseId={course.id} onOpenMistakes={() => setTab("mistakes")} />}
      </TabPanel>
      <TabPanel tabsId={id} value="mistakes" hidden={tab !== "mistakes"}>
        {tab === "mistakes" && <MistakesList courseId={course.id} />}
      </TabPanel>
    </div>
  );
}

/** Student progress: overview and mistakes notebook (`?tab=mistakes`). The server answers 404 for staff. */
export default function ProgressPage() {
  return (
    <Suspense fallback={null}>
      <ProgressTabs />
    </Suspense>
  );
}
