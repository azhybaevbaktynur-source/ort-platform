"use client";

// Phase 8c S3 (PHASE_8C_DESIGN §5.1): one page per assignment for staff. Header (title, kind, publish state, due date;
// "Publish"/"Unpublish" for non-quiz kinds, quizzes publish in the builder) and tabs picked by `?tab=`: Details,
// Submissions and grading (`GradingScreen`, `?filter=`) or Results for a quiz (`StaffAttemptList`), Settings
// (`AssignmentEditor`). A tab, once opened, stays mounted, so unsaved settings or an unsaved grade survive a tab switch.
// Back goes to the validated `?from=` (fallback: Assignments). The server decides every permission.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { getStaffAssignment, updateAssignment } from "@/lib/lms/assignments";
import type { AssignmentStaffOut } from "@/lib/lms/assignmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { StaffAttemptList } from "@/components/lms/results/StaffAttemptList";
import { Badge, Button, ConfirmDialog, EmptyState, LoadingState, PageHeader, TabPanel, Tabs, toast } from "@/components/ui";
import { AssignmentDetails } from "./AssignmentDetails";
import { AssignmentEditor, type AssignmentEditorHandle } from "./AssignmentEditor";
import { AssignmentError, KindBadge, useAssignmentErrorText } from "./assignmentUi";
import { GradingScreen } from "./GradingScreen";
import { BackLink, useObjectNav } from "./objectNav";

type TabId = "details" | "submissions" | "settings";
const TABS_ID = "assignment-page";

function tabOf(param: string | null): TabId {
  if (param === "settings") return "settings";
  if (param === "submissions" || param === "results") return "submissions";
  return "details";
}

export function AssignmentPage({ assignmentId }: { assignmentId: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const pathname = usePathname() ?? "";
  const search = useSearchParams();
  const canEdit = useCanEditContent();
  const errorText = useAssignmentErrorText();
  const base = `/${lang}/courses/${course.id}`;
  const nav = useObjectNav(`${base}/assignments`);
  const [a, setA] = useState<AssignmentStaffOut | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [pubBusy, setPubBusy] = useState(false);
  const [pubError, setPubError] = useState<unknown>(null);
  // Phase 7a UX kept: publishing with unsaved settings asks to save first (value = the wanted published state)
  const [pubAsk, setPubAsk] = useState<boolean | null>(null);
  const [unpubAsk, setUnpubAsk] = useState(false);
  const editorRef = useRef<AssignmentEditorHandle>(null);

  const tab = tabOf(search?.get("tab") ?? null);
  const filter = search?.get("filter") ?? null;
  const [visited, setVisited] = useState<Set<TabId>>(() => new Set([tab]));
  useEffect(() => { setVisited((v) => (v.has(tab) ? v : new Set(v).add(tab))); }, [tab]);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setA(await getStaffAssignment(course.id, assignmentId));
    } catch (e) {
      setLoadError(e);
    }
  }, [course.id, assignmentId]);
  useEffect(() => { void load(); }, [load]);

  const replaceQuery = (patch: Record<string, string | null>) => {
    const p = new URLSearchParams(search?.toString() ?? "");
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) p.delete(k);
      else p.set(k, v);
    }
    const qs = p.toString();
    router.replace(`${pathname}${qs ? `?${qs}` : ""}`, { scroll: false });
  };

  const quiz = a?.kind === "quiz";
  const switchTab = (id: string) => {
    const next = id as TabId;
    replaceQuery({ tab: next === "submissions" && quiz ? "results" : next, ...(next === "submissions" ? {} : { filter: null }) });
  };

  const title = a ? pickLocalized(a.title, lang, course.default_language) || t("assignments.untitled") : "";

  if (loadError && !a) {
    return (
      <div className="space-y-4">
        <BackLink nav={nav} />
        <PageHeader title={t("assignments.editor.title")} />
        <AssignmentError error={loadError} onRetry={() => void load()} />
      </div>
    );
  }
  if (!a) return <LoadingState rows={3} />;

  const preset = a.assessment?.preset ?? null;
  const ort = !!preset && preset !== "none";

  const setPublished = async (value: boolean): Promise<boolean> => {
    setPubBusy(true);
    setPubError(null);
    try {
      const out = await updateAssignment(course.id, a.id, { published: value });
      setA(out);
      toast.success(value ? t("assignments.editor.publishedToast") : t("assignments.editor.unpublishedToast"));
      return true;
    } catch (err) {
      setPubError(err);
      return false;
    } finally {
      setPubBusy(false);
    }
  };
  const askPublish = (value: boolean) => {
    setPubError(null);
    if (editorRef.current?.isDirty()) { setPubAsk(value); return; }
    if (!value && (a.counts.submitted > 0 || a.counts.graded > 0)) { setUnpubAsk(true); return; }
    void setPublished(value);
  };
  const saveThenPublish = async () => {
    if (pubAsk === null) return;
    const value = pubAsk;
    const ok = (await editorRef.current?.save()) ?? true;
    setPubAsk(null);
    if (ok) await setPublished(value);
    else switchTab("settings"); // the form shows why it was not saved
  };

  const publishButton = !quiz && canEdit && !a.deleted_at ? (
    <Button variant={a.published ? "secondary" : "primary"} loading={pubBusy} onClick={() => askPublish(!a.published)}>
      {a.published ? t("assignments.list.unpublish") : t("assignments.page.publish")}
    </Button>
  ) : undefined;
  const due = a.due_at ? t("assignments.page.dueLine", { date: fmtShortDateTime(a.due_at, lang) }) : t("assignments.page.noDue");
  const tabItems = [
    { id: "details", label: t("assignments.page.tabs.details") },
    quiz
      ? { id: "submissions", label: t("assignments.page.tabs.results") }
      : { id: "submissions", label: t("assignments.page.tabs.submissions"), count: a.counts.needs_grading || undefined },
    { id: "settings", label: t("assignments.page.tabs.settings") },
  ];

  return (
    <div>
      <BackLink nav={nav} />
      <PageHeader title={title} className="mb-4" description={due} primaryAction={publishButton}
        badge={(
          <>
            <KindBadge kind={a.kind} ort={ort} />
            {a.deleted_at ? <Badge tone="neutral">{t("assignments.list.deleted")}</Badge>
              : <Badge tone={a.published ? "success" : "neutral"}>{a.published ? t("assignments.list.publishedBadge") : t("assignments.list.draftBadge")}</Badge>}
          </>
        )} />
      {!unpubAsk && <AssignmentError error={pubError} className="mb-4" />}

      <Tabs id={TABS_ID} label={t("assignments.page.tabs.label")} value={tab} onChange={switchTab} items={tabItems} />

      {visited.has("details") && (
        <TabPanel tabsId={TABS_ID} value="details" hidden={tab !== "details"}>
          <AssignmentDetails assignment={a} nav={nav} />
        </TabPanel>
      )}
      {visited.has("submissions") && (
        <TabPanel tabsId={TABS_ID} value="submissions" hidden={tab !== "submissions"}>
          {quiz ? (
            a.assessment_id
              ? <StaffAttemptList courseId={course.id} assessmentId={a.assessment_id} embedded />
              : <EmptyState title={t("grading.empty")} />
          ) : (
            <GradingScreen assignmentId={a.id} embedded filter={filter}
              onFilterChange={(f) => replaceQuery({ filter: f === "all" ? null : f })} />
          )}
        </TabPanel>
      )}
      {visited.has("settings") && (
        <TabPanel tabsId={TABS_ID} value="settings" hidden={tab !== "settings"}>
          <AssignmentEditor ref={editorRef} assignment={a} onChange={setA} />
        </TabPanel>
      )}

      <ConfirmDialog open={pubAsk !== null} busy={pubBusy} title={t("assignments.editor.unsavedTitle")} object={title}
        effect={pubAsk ? t("assignments.editor.unsavedPublishBody") : t("assignments.editor.unsavedUnpublishBody")}
        confirmLabel={pubAsk ? t("assignments.editor.saveAndPublish") : t("assignments.editor.saveAndUnpublish")}
        onConfirm={() => void saveThenPublish()} onCancel={() => setPubAsk(null)} />
      <ConfirmDialog open={unpubAsk} busy={pubBusy} title={t("assignments.list.unpublishTitle")} object={title}
        effect={t("assignments.list.unpublishBody")} confirmLabel={t("assignments.list.unpublish")}
        error={pubError ? errorText(pubError) : undefined}
        onConfirm={() => void setPublished(false).then((ok) => { if (ok) setUnpubAsk(false); })} onCancel={() => setUnpubAsk(false)} />
    </div>
  );
}
