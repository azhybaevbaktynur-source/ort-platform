"use client";

// Phase 7b S4: template editor (PHASE_7B_DESIGN 10; no drag-and-drop constructor until 8b): structured header fields,
// Save (draft_rev conflict), Publish, Archive, Lock/Unlock (reason), Promote, Versions with the import-format download
// per version. S7 (UX fix): the structure is a form (`SpecForm`: defaults, section cards, parameters, lock scope;
// raw JSON only for the platform admin), server `spec_invalid` details translated under the matching field.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Archive, Download, TriangleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  archiveExamTemplate, downloadImportFormat, getExamTemplate, getExamTemplateBlocks, getExamTemplateVersion,
  listExamTemplateVersions, lockExamTemplate, patchExamTemplate, promoteExamTemplate, publishExamTemplate, unlockExamTemplate,
} from "@/lib/lms/examTemplates";
import type { BlocksOut, ExamTemplateOut, ExamTemplateSpec, ExamTemplateVersionOut, SpecIssue } from "@/lib/lms/examTemplateTypes";
import { AVAILABLE_DISPLAY_MODES, DISPLAY_MODES, NAVIGATIONS, PASSAGE_DISPLAYS, RESULT_VIEWS, passageRenderers, resultViews } from "@/lib/lms/blocks";
import type { Navigation } from "@/lib/lms/assessmentTypes";
import { cleanLocalized, pickLocalized } from "@/lib/lms/localized";
import { LMS_LANGS, type LocalizedText } from "@/lib/lms/types";
import { fmtDateTime } from "@/components/lms/assessments/format";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import {
  Button, Card, ConfirmDialog, ErrorState, LoadingState, MenuButton, PageHeader, ReasonDialog, Select, Table, toast,
  type Breadcrumb, type MenuItem, type TableColumn,
} from "@/components/ui";
import { STARTER_SPEC } from "./ExamTemplatesPage";
import {
  ExamTemplateError, LockedBadge, ScopeBadge, TemplateStatusBadge, locStartsWith, specIssuesOf, useExamTemplateErrorText, useSpecIssueText,
  type TemplateArea,
} from "./ui";
import { SpecForm } from "./SpecForm";
import { draftOf, specOf, type SpecDraft } from "./specDraft";

interface Form {
  title: LocalizedText;
  description: LocalizedText;
  spec: SpecDraft;
}

function formOf(tpl: ExamTemplateOut, spec: ExamTemplateSpec): Form {
  return { title: tpl.title ?? {}, description: tpl.description ?? {}, spec: draftOf(spec) };
}

type Action = "publish" | "archive" | "lock" | "unlock" | "promote";

export function ExamTemplateEditor({ area, templateId, crumbs }: {
  area: TemplateArea;
  templateId: string;
  crumbs: (title?: string) => Breadcrumb[];
}) {
  const { lang, t } = useTranslation();
  const errText = useExamTemplateErrorText();
  const [tpl, setTpl] = useState<ExamTemplateOut | null>(null);
  const [baseSpec, setBaseSpec] = useState<ExamTemplateSpec | null>(null);
  const [fromVersion, setFromVersion] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [blocks, setBlocks] = useState<BlocksOut | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [issues, setIssues] = useState<SpecIssue[]>([]);
  const [action, setAction] = useState<Action | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const seed = useCallback(async (x: ExamTemplateOut) => {
    let spec: ExamTemplateSpec | null = x.draft_spec ?? null;
    let from: number | null = null;
    if (!spec && x.current_version_no != null) {
      spec = x.current_spec ?? (await getExamTemplateVersion(x.id, x.current_version_no)).spec;
      from = x.current_version_no;
    }
    const s = spec ?? (STARTER_SPEC as ExamTemplateSpec);
    setTpl(x);
    setBaseSpec(s);
    setFromVersion(from);
    setForm(formOf(x, s));
    setDirty(false);
    setIssues([]);
  }, []);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      await seed(await getExamTemplate(templateId));
    } catch (e) {
      setLoadError(e);
    }
  }, [templateId, seed]);

  useEffect(() => { setTpl(null); void load(); }, [load]);
  useEffect(() => {
    let alive = true;
    getExamTemplateBlocks().then((b) => { if (alive) setBlocks(b); }).catch(() => { /* scheme list is optional */ });
    return () => { alive = false; };
  }, []);

  const fetchVersions = useCallback(() => listExamTemplateVersions(templateId), [templateId]);
  const versions = useCursorList(fetchVersions);
  const vState = useTableState(versions);

  const name = tpl ? pickLocalized(tpl.title, lang) || t("examTemplates.untitled") : "";
  const readOnly = !tpl || tpl.status === "archived" || (area.kind === "org" && !!area.readOnly);
  // S5: the server says who may lock (the owner) and promote (org admin of a teacher template's organization).
  const canLock = !!tpl?.can_lock;
  const canPromote = !!tpl?.can_promote;
  const hasDraft = !!tpl?.draft_spec;

  const update = <K extends "title" | "description">(k: K, v: Form[K]) => {
    setForm((f) => (f ? { ...f, [k]: v } : f));
    setDirty(true);
  };
  const updateSpec = useCallback((fn: (d: SpecDraft) => SpecDraft) => {
    setForm((f) => (f ? { ...f, spec: fn(f.spec) } : f));
    setDirty(true);
  }, []);
  const setSpecField = <K extends "navigation" | "displayMode" | "passageDisplay" | "resultView" | "schemeId">(k: K, v: SpecDraft[K]) =>
    updateSpec((d) => ({ ...d, [k]: v }));

  // S7: "Раздел «Теория»" in issue locations and selects ("Раздел 2" when untitled)
  const sectionName = useCallback((i: number) => {
    const s = form?.spec.sections[i];
    return pickLocalized(s?.title, lang) || t("examTemplates.picker.sectionN", { n: i + 1 });
  }, [form?.spec.sections, lang, t]);
  const issueText = useSpecIssueText(sectionName);
  const topIssue = (k: string) => {
    const hit = issues.filter((i) => locStartsWith(i.loc, [k]));
    return hit.length ? Array.from(new Set(hit.map(issueText.what))).join(" ") : undefined;
  };

  const save = async () => {
    if (!tpl || !form || !baseSpec) return;
    const spec = specOf(form.spec);
    const title = cleanLocalized(form.title, LMS_LANGS);
    if (Object.keys(title).length === 0) { setSaveError({ code: "title_required" }); return; }
    const description = cleanLocalized(form.description, LMS_LANGS);
    setSaving(true);
    setSaveError(null);
    setIssues([]);
    try {
      const out = await patchExamTemplate(tpl.id, {
        draft_rev: tpl.draft_rev ?? 1, title, description: Object.keys(description).length ? description : null, draft_spec: spec,
      });
      await seed(out);
      toast.success(t("examTemplates.editor.saved"));
    } catch (e) {
      setSaveError(e);
      setIssues(specIssuesOf(e));
      const code = (e as { code?: string }).code;
      if (code === "draft_conflict") toast.error(t("examTemplates.errors.draft_conflict"));
      else if (specIssuesOf(e).length) toast.error(t("examTemplates.editor.issues", { n: specIssuesOf(e).length }));
    } finally {
      setSaving(false);
    }
  };

  const run = async (a: Action, reason = "") => {
    if (!tpl) return;
    setActionBusy(true);
    setActionError(null);
    try {
      const published = a === "publish" ? await publishExamTemplate(tpl.id) : null;
      const out = published ? published.template
        : a === "archive" ? await archiveExamTemplate(tpl.id)
          : a === "lock" ? await lockExamTemplate(tpl.id, reason)
            : a === "unlock" ? await unlockExamTemplate(tpl.id, reason)
              : await promoteExamTemplate(tpl.id);
      await seed(out);
      setAction(null);
      if (a === "publish") void versions.reload();
      toast.success(published
        ? t(published.unchanged ? "examTemplates.publish.unchanged" : "examTemplates.publish.done", { n: published.version.version_no })
        : t(`examTemplates.${a}.done`));
    } catch (e) {
      setActionError(e);
      if (a === "publish") setIssues(specIssuesOf(e));
    } finally {
      setActionBusy(false);
    }
  };

  const schemeOptions = useMemo(() => {
    const rows = blocks?.scheme_versions ?? [];
    const opts = rows.map((s) => ({
      value: s.id,
      label: `${typeof s.title === "string" ? s.title : pickLocalized(s.title, lang) || s.id} · ${t(`examTemplates.editor.schemeScope.${s.scope}`)}`,
    }));
    const current = form?.spec.schemeId;
    if (current && !rows.some((s) => s.id === current)) opts.unshift({ value: current, label: t("examTemplates.editor.schemeCurrent") });
    return [{ value: "", label: t("examTemplates.editor.schemeNone") }, ...opts];
  }, [blocks, form?.spec.schemeId, lang, t]);

  if (loadError && !tpl) {
    const status = (loadError as { status?: number }).status;
    return (
      <div>
        <PageHeader title={t("examTemplates.list.pageTitle")} breadcrumbs={crumbs()} />
        <ErrorState title={status === 404 ? t("examTemplates.editor.notFound") : undefined} message={errText(loadError)} onRetry={status === 404 ? undefined : () => void load()} />
      </div>
    );
  }
  if (!tpl || !form) return <LoadingState label={t("lms.common.loading")} />;

  const menu: MenuItem[] = [
    ...(canLock && !tpl.locked ? [{ id: "lock", label: t("examTemplates.lock.action"), description: t("examTemplates.lock.menuHint") }] : []),
    ...(canLock && tpl.locked ? [{ id: "unlock", label: t("examTemplates.unlock.action"), description: t("examTemplates.unlock.menuHint") }] : []),
    ...(canPromote ? [{ id: "promote", label: t("examTemplates.promote.action"), description: t("examTemplates.promote.menuHint") }] : []),
    ...(tpl.status !== "archived" ? [{ id: "archive", label: t("examTemplates.archive.action"), description: t("examTemplates.archive.menuHint") }] : []),
  ];
  const publishPrimary = !dirty && hasDraft;
  const saveButton = (
    <Button variant={publishPrimary ? "secondary" : "primary"} loading={saving} disabled={readOnly || !dirty} onClick={() => void save()}>
      {t("examTemplates.editor.save")}
    </Button>
  );
  const publishButton = (
    <Button variant={publishPrimary ? "primary" : "secondary"} disabled={readOnly || dirty || !hasDraft} onClick={() => { setActionError(null); setAction("publish"); }}>
      {t("examTemplates.publish.action")}
    </Button>
  );

  const versionColumns: TableColumn<ExamTemplateVersionOut>[] = [
    { key: "no", header: t("examTemplates.versions.version"), primary: true, cell: (v) => <span className="font-semibold">{t("examTemplates.versionShort", { n: v.version_no })}</span> },
    { key: "published", header: t("examTemplates.versions.published"), nowrap: true, cell: (v) => fmtDateTime(v.published_at) },
    { key: "sections", header: t("examTemplates.versions.sections"), align: "right", cell: (v) => v.spec?.sections?.length ?? "—" },
    { key: "actions", header: t("examTemplates.versions.importFormat"), actions: true, cell: (v) => <ImportFormatButton templateId={tpl.id} versionNo={v.version_no} /> },
  ];

  const objectName = <strong className="break-words">{name}</strong>;
  return (
    <div className="space-y-6">
      <PageHeader
        title={name}
        breadcrumbs={crumbs(name)}
        badge={<span className="inline-flex flex-wrap gap-1.5"><ScopeBadge scope={tpl.owner_scope} /><TemplateStatusBadge status={tpl.status} />{tpl.locked && <LockedBadge />}</span>}
        description={tpl.current_version_no != null ? t("examTemplates.editor.currentVersion", { n: tpl.current_version_no }) : t("examTemplates.editor.noVersion")}
        primaryAction={readOnly ? undefined : (publishPrimary ? publishButton : saveButton)}
        secondaryActions={readOnly ? undefined : (
          <>
            {publishPrimary ? saveButton : publishButton}
            {menu.length > 0 && <MenuButton label={t("examTemplates.editor.more")} items={menu} variant="secondary" align="end" onSelect={(id) => { setActionError(null); setAction(id as Action); }} />}
          </>
        )}
      />

      {tpl.status === "archived" && (
        <p role="status" className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
          <Archive className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />{t("examTemplates.editor.archivedNote")}
        </p>
      )}
      {!readOnly && fromVersion != null && !hasDraft && <p role="note" className="text-sm text-slate-600">{t("examTemplates.editor.fromVersion", { n: fromVersion })}</p>}
      {!readOnly && dirty && <p role="status" className="text-sm font-medium text-warning-900">{t("examTemplates.editor.unsaved")}</p>}
      {!readOnly && !dirty && hasDraft && tpl.current_version_no != null && <p role="note" className="text-sm text-slate-600">{t("examTemplates.editor.draftPending")}</p>}

      <Card className="space-y-5">
        <h2 className="text-lg font-semibold text-slate-900">{t("examTemplates.editor.general")}</h2>
        <LocalizedTextInput label={t("examTemplates.fields.title")} languages={LMS_LANGS} defaultLanguage={lang} value={form.title}
          onChange={(v) => update("title", v)} maxLength={200} required disabled={readOnly} />
        <LocalizedTextInput label={t("examTemplates.fields.description")} languages={LMS_LANGS} defaultLanguage={lang} value={form.description}
          onChange={(v) => update("description", v)} maxLength={2000} multiline disabled={readOnly} />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Select label={t("examTemplates.editor.navigation")} value={form.spec.navigation} disabled={readOnly} error={topIssue("navigation")}
            onChange={(e) => setSpecField("navigation", e.target.value as Navigation)}
            options={NAVIGATIONS.map((n) => ({ value: n, label: t(`assessments.navigation.${n}`) }))} />
          <Select label={t("examTemplates.editor.displayMode")} value={form.spec.displayMode} disabled={readOnly} error={topIssue("display_mode")}
            hint={t("examTemplates.scrollingLater")} onChange={(e) => setSpecField("displayMode", e.target.value)}
            options={DISPLAY_MODES.map((m) => ({ value: m, label: t(`examTemplates.blocks.displayModes.${m}`), disabled: !AVAILABLE_DISPLAY_MODES.includes(m) }))} />
          <Select label={t("examTemplates.editor.passageDisplay")} value={form.spec.passageDisplay} disabled={readOnly} error={topIssue("passage_display")}
            onChange={(e) => setSpecField("passageDisplay", e.target.value)}
            options={[{ value: "", label: t("examTemplates.editor.courseDefault") }, ...PASSAGE_DISPLAYS.map((p) => ({ value: p, label: t(passageRenderers[p].titleKey) }))]} />
          <Select label={t("examTemplates.editor.resultView")} value={form.spec.resultView} disabled={readOnly} error={topIssue("result_view")}
            onChange={(e) => setSpecField("resultView", e.target.value)}
            options={[{ value: "", label: t("examTemplates.editor.courseDefault") }, ...RESULT_VIEWS.map((r) => ({ value: r, label: t(resultViews[r].titleKey) }))]} />
          <Select label={t("examTemplates.editor.scheme")} value={form.spec.schemeId} disabled={readOnly} containerClassName="sm:col-span-2"
            hint={t(tpl.owner_scope === "teacher" ? "examTemplates.editor.schemeHintTeacher" : "examTemplates.editor.schemeHintShared")}
            error={topIssue("scoring")} onChange={(e) => setSpecField("schemeId", e.target.value)} options={schemeOptions} />
        </div>
      </Card>

      <SpecForm draft={form.spec} update={updateSpec} readOnly={readOnly} issues={issues} blocks={blocks}
        platform={area.kind === "platform"} sectionName={sectionName} />

      <div className="space-y-3">
        {issues.length > 0 && (
          <div role="alert" className="rounded-xl border border-danger-200 bg-danger-50 px-3.5 py-3 text-sm text-danger-800">
            <p className="flex items-center gap-2 font-semibold"><TriangleAlert className="h-4 w-4" aria-hidden="true" />{t("examTemplates.editor.issues", { n: issues.length })}</p>
            <ul className="mt-2 space-y-1">
              {issues.map((i, idx) => (
                <li key={idx} className="break-words"><span className="font-medium">{issueText.where(i.loc)}</span>: {issueText.what(i)}</li>
              ))}
            </ul>
          </div>
        )}
        {saveError && (saveError as { code?: string }).code === "draft_conflict" ? (
          <ErrorState variant="inline" message={t("examTemplates.editor.conflict")}
            action={<Button variant="secondary" size="sm" onClick={() => void load()}>{t("examTemplates.editor.reload")}</Button>} />
        ) : (saveError as { code?: string } | null)?.code === "title_required" ? (
          <p role="alert" className="text-sm text-danger-700">{t("examTemplates.fields.titleRequired")}</p>
        ) : issues.length === 0 && <ExamTemplateError error={saveError} />}
        {!readOnly && dirty && (
          <div className="flex flex-wrap items-center gap-3">
            {saveButton}
            <p className="text-sm font-medium text-warning-900">{t("examTemplates.editor.unsaved")}</p>
          </div>
        )}
      </div>

      <section aria-labelledby="tpl-versions" className="space-y-3">
        <h2 id="tpl-versions" className="text-lg font-semibold text-slate-900">{t("examTemplates.versions.title")}</h2>
        <p className="text-sm text-slate-600">{t("examTemplates.importFormat.help")}</p>
        <Table caption={t("examTemplates.versions.title")} columns={versionColumns} rows={versions.items} rowKey={(v) => v.id} {...vState}
          empty={<p className="px-4 py-6 text-center text-sm text-slate-600">{t("examTemplates.versions.empty")}</p>} />
        <MoreError list={versions} />
      </section>

      <ConfirmDialog open={action === "publish"} title={t("examTemplates.publish.title")} object={objectName}
        effect={t("examTemplates.publish.effect", { n: (tpl.current_version_no ?? 0) + 1 })} confirmLabel={t("examTemplates.publish.action")}
        cancelLabel={t("ui.cancel")} busy={actionBusy} error={actionError ? errText(actionError) : undefined}
        onConfirm={() => void run("publish")} onCancel={() => setAction(null)} />
      <ConfirmDialog open={action === "archive"} tone="danger" title={t("examTemplates.archive.title")} object={objectName}
        effect={t("examTemplates.archive.effect")} confirmLabel={t("examTemplates.archive.action")}
        cancelLabel={t("ui.cancel")} busy={actionBusy} error={actionError ? errText(actionError) : undefined}
        onConfirm={() => void run("archive")} onCancel={() => setAction(null)} />
      <ConfirmDialog open={action === "promote"} title={t("examTemplates.promote.title")} object={objectName}
        effect={t("examTemplates.promote.effect")} confirmLabel={t("examTemplates.promote.action")}
        cancelLabel={t("ui.cancel")} busy={actionBusy} error={actionError ? errText(actionError) : undefined}
        onConfirm={() => void run("promote")} onCancel={() => setAction(null)} />
      <ReasonDialog open={action === "lock" || action === "unlock"} optional maxLength={500}
        title={t(action === "unlock" ? "examTemplates.unlock.title" : "examTemplates.lock.title")} object={objectName}
        effect={t(action === "unlock" ? "examTemplates.unlock.effect" : "examTemplates.lock.effect")}
        confirmLabel={t(action === "unlock" ? "examTemplates.unlock.action" : "examTemplates.lock.action")}
        reasonLabel={t("examTemplates.lock.reason")}
        cancelLabel={t("ui.cancel")} busy={actionBusy} error={actionError ? errText(actionError) : undefined}
        onConfirm={(reason) => void run(action === "unlock" ? "unlock" : "lock", reason)} onCancel={() => setAction(null)} />
    </div>
  );
}

function ImportFormatButton({ templateId, versionNo }: { templateId: string; versionNo: number }) {
  const { lang, t } = useTranslation();
  const errText = useExamTemplateErrorText();
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try {
      await downloadImportFormat(templateId, versionNo, lang);
      toast.success(t("examTemplates.importFormat.downloaded"));
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button variant="secondary" size="sm" loading={busy} leftIcon={<Download className="h-4 w-4" aria-hidden="true" />}
      aria-label={t("examTemplates.importFormat.downloadVersion", { n: versionNo })} onClick={() => void go()}>
      {t("examTemplates.importFormat.csv")}
    </Button>
  );
}
