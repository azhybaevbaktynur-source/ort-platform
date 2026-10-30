"use client";

// Phase 8c S3 (PHASE_8C_DESIGN §5.2): one page per page for staff. Back (validated `?from=`, fallback the Course page),
// the page title with its state, and two tabs picked by `?tab=`: Edit (`PageEditor` as before: language variants,
// publish switch, conflict dialog) and Preview (`PageView` of the saved page, with the language variant chips).
// The editor stays mounted while Preview is open, so unsaved text survives a look at the preview; Preview loads the
// saved page each time it opens.
import React, { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import type { PageStaffOut } from "@/lib/lms/pagesTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { BackLink, maybeFrom, useObjectNav } from "@/components/lms/assignments/objectNav";
import { Badge, PageHeader, TabPanel, Tabs } from "@/components/ui";
import { PageEditor } from "./PageEditor";
import { PageView } from "./PageView";

type TabId = "edit" | "preview";
const TABS_ID = "page-object";

export function PageObject({ pageId }: { pageId: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const pathname = usePathname() ?? "";
  const search = useSearchParams();
  const canEdit = useCanEditContent();
  const base = `/${lang}/courses/${course.id}`;
  const nav = useObjectNav();
  const [page, setPage] = useState<PageStaffOut | null>(null);
  const param = search?.get("tab");
  // a concluded course is read-only: Preview first
  const tab: TabId = param === "preview" || param === "edit" ? param : canEdit ? "edit" : "preview";

  const switchTab = (id: string) => {
    const p = new URLSearchParams(search?.toString() ?? "");
    p.set("tab", id);
    router.replace(`${pathname}?${p}`, { scroll: false });
  };

  return (
    <div className="max-w-4xl">
      <BackLink nav={nav} />
      <PageHeader title={page?.title || t("pages.editor.editTitle")} className="mb-4"
        badge={page ? <Badge tone={page.published ? "success" : "neutral"}>{t(page.published ? "pages.published" : "pages.draft")}</Badge> : undefined} />
      <Tabs id={TABS_ID} label={t("pages.object.tabs.label")} value={tab} onChange={switchTab} items={[
        { id: "edit", label: t("pages.object.tabs.edit") },
        { id: "preview", label: t("pages.object.tabs.preview") },
      ]} />
      <TabPanel tabsId={TABS_ID} value="edit" hidden={tab !== "edit"}>
        <PageEditor pageId={pageId} embedded onPage={setPage} />
      </TabPanel>
      {tab === "preview" && (
        <TabPanel tabsId={TABS_ID} value="preview">
          <p className="mb-4 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{t("pages.object.previewNote")}</p>
          <PageView pageId={pageId}
            preview={{ variantHref: (id) => maybeFrom(`${base}/pages/${id}?tab=preview`, nav.from) }} />
        </TabPanel>
      )}
    </div>
  );
}
