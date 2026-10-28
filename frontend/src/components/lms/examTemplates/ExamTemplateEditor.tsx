"use client";

// Phase 8b S4: the exam template constructor (PHASE_8B_DESIGN 9), replacing the 7b plain form. One page shell with
// a header (status, Publish, Preview, More) and tabs Structure · Scoring · Display · Sample questions · Versions.
// The draft autosaves (`useConstructor`); every pick list comes from `GET /exam-templates/blocks`; server
// `spec_invalid` details show next to their fields and in the issues bar. Shared by the teacher area
// (/exam-templates/[id]), the organization area and the platform admin area.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Archive, Lock, RotateCcw } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  archiveExamTemplate, downloadImportFormat, getExamTemplateBlocks, lockExamTemplate, promoteExamTemplate, publishExamTemplate,
  unlockExamTemplate,
} from "@/lib/lms/examTemplates";
import type { BlocksOut, ExamTemplateOut } from "@/lib/lms/examTemplateTypes";
import { pickLocalized } from "@/lib/lms/localized";
import {
  Button, ConfirmDialog, ErrorState, LoadingState, PageHeader, ReasonDialog, TabPanel, Tabs, toast, type Breadcrumb,
} from "@/components/ui";
import { DraftConflictDialog } from "@/components/lms/quiz/DraftConflictDialog";
import { useExamTemplateErrorText, useSpecIssueText, type TemplateArea } from "./ui";
import { ConstructorHeader, type HeaderAction } from "./ConstructorHeader";
import { IssuesBar } from "./IssuesBar";
import { StructureTab } from "./StructureTab";
import { ScoringTab } from "./ScoringTab";
import { DisplayTab } from "./DisplayTab";
import { SampleTab } from "./SampleTab";
import { VersionsTab } from "./VersionsTab";
import { fieldId, tabOfLoc, useFieldIssues, type ConstructorTab } from "./parts";
import { useConstructor } from "./useConstructor";

const TABS: ConstructorTab[] = ["structure", "scoring", "display", "sample", "versions"];
type DialogAction = Exclude<HeaderAction, "importFormat">;

export function ExamTemplateEditor({ area, templateId, crumbs }: {
  area: TemplateArea;
  templateId: string;
  crumbs: (title?: string) => Breadcrumb[];
}) {
  const { lang, t } = useTranslation();
  const errText = useExamTemplateErrorText();
  const areaReadOnly = area.kind === "org" && !!area.readOnly;
  // Locked or archived templates are read-only (PHASE_8B_DESIGN 9.2); the owner unlocks from the More menu.
  const readOnlyOf = useCallback((x: ExamTemplateOut) => x.status === "archived" || !!x.locked || areaReadOnly, [areaReadOnly]);
  const c = useConstructor(templateId, { readOnly: readOnlyOf });
  const { tpl, draft } = c;

  const [blocks, setBlocks] = useState<BlocksOut | null>(null);
  const [blocksError, setBlocksError] = useState<unknown>(null);
  const [blocksTry, setBlocksTry] = useState(0);
  const [tab, setTabState] = useState<ConstructorTab>("structure");
  const [visited, setVisited] = useState<Set<ConstructorTab>>(() => new Set(["structure"]));
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [action, setAction] = useState<DialogAction | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [versionsKey, setVersionsKey] = useState(0);
  const [conflictHidden, setConflictHidden] = useState(false);

  useEffect(() => {
    let alive = true;
    setBlocksError(null);
    getExamTemplateBlocks().then((b) => { if (alive) setBlocks(b); }).catch((e) => { if (alive) setBlocksError(e); });
    return () => { alive = false; };
  }, [blocksTry]);

  const setTab = useCallback((next: ConstructorTab) => {
    setTabState(next);
    setVisited((v) => (v.has(next) ? v : new Set(v).add(next)));
    // the tab is kept in the URL so the preview's `return` link lands on the Sample tab
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", next);
      window.history.replaceState(window.history.state, "", url.toString());
    } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    try {
      const q = new URLSearchParams(window.location.search).get("tab") as ConstructorTab | null;
      if (q && TABS.includes(q) && q !== "structure") setTab(q);
    } catch { /* ignore */ }
  }, [setTab]);

  const sectionName = useCallback((i: number) => {
    const s = draft?.sections[i];
    return pickLocalized(s?.title, lang) || t("examTemplates.picker.sectionN", { n: i + 1 });
  }, [draft?.sections, lang, t]);
  const { what } = useSpecIssueText(sectionName);
  const err = useFieldIssues(c.issues, what);
  const readOnly = !tpl || readOnlyOf(tpl);
  useEffect(() => { if (c.saveState === "conflict") setConflictHidden(false); }, [c.saveState]);
  // a template with a single section opens with that section expanded (nothing to choose between)
  const firstUid = draft?.sections.length === 1 ? draft.sections[0].uid : null;
  useEffect(() => { if (firstUid) setExpanded((x) => (x.size ? x : new Set([firstUid]))); }, [firstUid]);

  const goTo = useCallback((loc: (string | number)[]) => {
    setTab(tabOfLoc(loc));
    if (String(loc[0]) === "sections" && loc[1] !== undefined && /^\d+$/.test(String(loc[1])) && draft) {
      const s = draft.sections[Number(loc[1])];
      if (s) setExpanded((x) => new Set(x).add(s.uid));
    }
    requestAnimationFrame(() => requestAnimationFrame(() => {
      for (let n = loc.length; n > 0; n--) {
        const el = document.getElementById(fieldId(...loc.slice(0, n)));
        if (!el) continue;
        el.scrollIntoView({ block: "center" });
        const focusable = el.matches("input,select,textarea,button") ? el
          : el.querySelector<HTMLElement>("input:not([disabled]),select:not([disabled]),textarea:not([disabled]),button:not([disabled])");
        focusable?.focus({ preventScroll: true });
        return;
      }
    }));
  }, [draft, setTab]);

  const name = tpl ? pickLocalized(c.meta.title, lang) || pickLocalized(tpl.title, lang) || t("examTemplates.untitled") : "";
  const objectName = <strong className="break-words">{name}</strong>;
  const hasDraft = !!tpl?.draft_spec;
  const dirty = c.saveState === "dirty" || c.saveState === "saving" || c.saveState === "invalid" || c.saveState === "error" || c.saveState === "conflict";
  const canPublish = !readOnly && (hasDraft || dirty) && c.saveState !== "conflict";

  const onHeaderAction = (a: HeaderAction) => {
    if (a === "importFormat") {
      if (tpl?.current_version_no == null) return;
      downloadImportFormat(tpl.id, tpl.current_version_no, lang)
        .then(() => toast.success(t("examTemplates.importFormat.downloaded")))
        .catch((e) => toast.error(errText(e)));
      return;
    }
    setActionError(null);
    setAction(a);
  };

  const run = async (a: DialogAction, reason = "") => {
    if (!tpl) return;
    setActionBusy(true);
    setActionError(null);
    try {
      // unsaved edits go first, so nothing typed is lost by the reload that follows
      const saved = await c.flush();
      if (a === "publish" && !saved) {
        setActionError({ code: "constructor_unsaved" });
        return;
      }
      const published = a === "publish" ? await publishExamTemplate(tpl.id) : null;
      const out = published ? published.template
        : a === "archive" ? await archiveExamTemplate(tpl.id)
          : a === "lock" ? await lockExamTemplate(tpl.id, reason)
            : a === "unlock" ? await unlockExamTemplate(tpl.id, reason)
              : await promoteExamTemplate(tpl.id);
      await c.replace(out);
      setAction(null);
      if (a === "publish") setVersionsKey((k) => k + 1);
      toast.success(published
        ? t(published.unchanged ? "examTemplates.constructor.publishUnchanged" : "examTemplates.publish.done", { n: published.version.version_no })
        : t(`examTemplates.${a}.done`));
    } catch (e) {
      setActionError(e);
    } finally {
      setActionBusy(false);
    }
  };
  const actionErrorText = actionError
    ? ((actionError as { code?: string }).code === "constructor_unsaved" ? t("examTemplates.constructor.publishBlocked") : errText(actionError))
    : undefined;

  const tabItems = useMemo(() => TABS.map((id) => ({
    id,
    label: t(`examTemplates.constructor.tabs.${id}`),
    count: id === "structure" && draft ? draft.sections.length : undefined,
  })), [t, draft]);

  if (c.loadError && !tpl) {
    const status = (c.loadError as { status?: number }).status;
    return (
      <div>
        <PageHeader title={t("examTemplates.list.pageTitle")} breadcrumbs={crumbs()} />
        <ErrorState title={status === 404 ? t("examTemplates.editor.notFound") : undefined} message={errText(c.loadError)}
          onRetry={status === 404 ? undefined : () => void c.load()} />
      </div>
    );
  }
  if (!tpl || !draft) return <LoadingState label={t("lms.common.loading")} />;

  const tabProps = { draft, update: c.update, readOnly, err, sectionName };
  const blocksGate = (body: (b: BlocksOut) => React.ReactNode) => blocksError && !blocks
    ? <ErrorState variant="inline" message={t("examTemplates.constructor.blocksError")} onRetry={() => setBlocksTry((n) => n + 1)} />
    : !blocks ? <LoadingState rows={3} label={t("lms.common.loading")} /> : body(blocks);

  return (
    <div className="space-y-5">
      <ConstructorHeader tpl={tpl} name={name} crumbs={crumbs(name)} readOnly={readOnly} saveState={c.saveState}
        issueCount={c.issues.length} canPublish={canPublish} onAction={onHeaderAction} onPreview={() => setTab("sample")}
        onRetrySave={() => (c.saveState === "conflict" ? setConflictHidden(false) : void c.flush())} />

      {tpl.status === "archived" ? (
        <p role="status" className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
          <Archive className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />{t("examTemplates.editor.archivedNote")}
        </p>
      ) : tpl.locked ? (
        <p role="status" className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
          <Lock className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {t(tpl.can_lock ? "examTemplates.constructor.lockedOwner" : "examTemplates.constructor.lockedOther")}
        </p>
      ) : areaReadOnly ? (
        <p role="status" className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{t("examTemplates.constructor.readOnlyArea")}</p>
      ) : null}

      {c.restore && !readOnly && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-warning-200 bg-warning-50 px-3.5 py-3 text-sm text-warning-900">
          <RotateCcw className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0 flex-1 basis-[14rem]">
            <span className="block font-semibold">{t("examTemplates.constructor.restoreDraft.title")}</span>
            {t("examTemplates.constructor.restoreDraft.body")}
          </span>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={c.acceptRestore}>{t("examTemplates.constructor.restoreDraft.restore")}</Button>
            <Button size="sm" variant="secondary" onClick={c.discardRestore}>{t("examTemplates.constructor.restoreDraft.discard")}</Button>
          </div>
        </div>
      )}
      {!readOnly && c.fromVersion != null && !hasDraft && c.saveState === "idle" && (
        <p role="note" className="text-sm text-slate-600">{t("examTemplates.editor.fromVersion", { n: c.fromVersion })}</p>
      )}
      {c.saveState === "error" && <ErrorState variant="inline" message={errText(c.saveError)} onRetry={() => void c.flush()} />}

      {tab !== "sample" && tab !== "versions" && <IssuesBar issues={c.issues} sectionName={sectionName} onGoTo={goTo} />}

      <Tabs id="tpl-constructor" label={t("examTemplates.constructor.tabs.label")} value={tab} onChange={(id) => setTab(id as ConstructorTab)} items={tabItems} />

      <TabPanel tabsId="tpl-constructor" value="structure" hidden={tab !== "structure"}>
        {blocksGate((b) => (
          <StructureTab {...tabProps} meta={c.meta} setMeta={c.setMeta} blocks={b} platform={area.kind === "platform"}
            expanded={expanded} setExpanded={setExpanded} />
        ))}
      </TabPanel>
      <TabPanel tabsId="tpl-constructor" value="scoring" hidden={tab !== "scoring"}>
        {visited.has("scoring") && blocksGate((b) => <ScoringTab {...tabProps} blocks={b} scope={tpl.owner_scope} />)}
      </TabPanel>
      <TabPanel tabsId="tpl-constructor" value="display" hidden={tab !== "display"}>
        {visited.has("display") && blocksGate((b) => <DisplayTab {...tabProps} blocks={b} />)}
      </TabPanel>
      <TabPanel tabsId="tpl-constructor" value="sample" hidden={tab !== "sample"}>
        {visited.has("sample") && (
          <SampleTab tpl={tpl} draft={draft} active={tab === "sample"} archived={tpl.status === "archived"} saveState={c.saveState}
            flush={c.flush} />
        )}
      </TabPanel>
      <TabPanel tabsId="tpl-constructor" value="versions" hidden={tab !== "versions"}>
        {visited.has("versions") && (
          <VersionsTab tpl={tpl} blocks={blocks} canDiffDraft={hasDraft && !areaReadOnly} reloadKey={versionsKey} />
        )}
      </TabPanel>

      <ConfirmDialog open={action === "publish"} title={t("examTemplates.publish.title")} object={objectName}
        effect={t("examTemplates.publish.effect", { n: (tpl.current_version_no ?? 0) + 1 })} confirmLabel={t("examTemplates.publish.action")}
        cancelLabel={t("ui.cancel")} busy={actionBusy} error={actionErrorText}
        onConfirm={() => void run("publish")} onCancel={() => setAction(null)} />
      <ConfirmDialog open={action === "archive"} tone="danger" title={t("examTemplates.archive.title")} object={objectName}
        effect={t("examTemplates.archive.effect")} confirmLabel={t("examTemplates.archive.action")}
        cancelLabel={t("ui.cancel")} busy={actionBusy} error={actionErrorText}
        onConfirm={() => void run("archive")} onCancel={() => setAction(null)} />
      <ConfirmDialog open={action === "promote"} title={t("examTemplates.promote.title")} object={objectName}
        effect={t("examTemplates.promote.effect")} confirmLabel={t("examTemplates.promote.action")}
        cancelLabel={t("ui.cancel")} busy={actionBusy} error={actionErrorText}
        onConfirm={() => void run("promote")} onCancel={() => setAction(null)} />
      <ReasonDialog open={action === "lock" || action === "unlock"} optional maxLength={500}
        title={t(action === "unlock" ? "examTemplates.unlock.title" : "examTemplates.lock.title")} object={objectName}
        effect={t(action === "unlock" ? "examTemplates.unlock.effect" : "examTemplates.lock.effect")}
        confirmLabel={t(action === "unlock" ? "examTemplates.unlock.action" : "examTemplates.lock.action")}
        reasonLabel={t("examTemplates.lock.reason")}
        cancelLabel={t("ui.cancel")} busy={actionBusy} error={actionErrorText}
        onConfirm={(reason) => void run(action === "unlock" ? "unlock" : "lock", reason)} onCancel={() => setAction(null)} />
      <DraftConflictDialog kind={c.saveState === "conflict" && !conflictHidden ? "draft" : null} busy={c.conflictBusy}
        copy={{
          title: t("examTemplates.constructor.conflict.title"), body: t("examTemplates.constructor.conflict.body"),
          takeTheirs: t("examTemplates.constructor.conflict.takeTheirs"), keepMine: t("examTemplates.constructor.conflict.keepMine"),
        }}
        onPrimary={() => void c.keepMine()} onSecondary={() => void c.takeTheirs()} onClose={() => setConflictHidden(true)} />
    </div>
  );
}
