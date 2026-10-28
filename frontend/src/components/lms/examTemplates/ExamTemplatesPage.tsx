"use client";

// Phase 7b S4: the exam templates list, shared by /exam-templates (teacher, mine), /org/[orgId]/exam-templates (org
// admins) and /admin/exam-templates (platform) (PHASE_7B_DESIGN 10). The server scopes the list (management mode).
import React, { useCallback, useEffect, useId, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LayoutTemplate, Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { DEFAULT_DISPLAY_MODE, NEW_SECTION_EXCLUDED_TYPES, createExamTemplate, getExamTemplateBlocks, listExamTemplates } from "@/lib/lms/examTemplates";
import {
  EXAM_TEMPLATE_STATUSES, type BlocksOut, type ExamTemplateOut, type ExamTemplateScope, type ExamTemplateSpec, type ExamTemplateStatus,
} from "@/lib/lms/examTemplateTypes";
import type { DisplayMode } from "@/lib/lms/blocks";
import { listMyOrganizations, type MyOrganizationOut } from "@/lib/lms/organizations";
import { cleanLocalized, pickLocalized } from "@/lib/lms/localized";
import { LMS_LANGS, type LocalizedText } from "@/lib/lms/types";
import { fmtDateTime } from "@/components/lms/assessments/format";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import {
  Button, Dialog, EmptyState, FilterBar, PageHeader, Select, Table, type Breadcrumb, type TableColumn,
} from "@/components/ui";
import { ExamTemplateError, LockedBadge, ScopeBadge, TemplateStatusBadge, type TemplateArea } from "./ui";
import { RadioCards } from "./parts";

/**
 * Starter draft of a new template (Phase 8b S4): one section with every catalog type except the ORT-only ones, and
 * the display mode chosen in the "New template" dialog. Navigation and import format take the server defaults.
 */
export function starterSpec(blocks: BlocksOut, displayMode: string): ExamTemplateSpec {
  const excluded = NEW_SECTION_EXCLUDED_TYPES as readonly string[];
  return {
    schema: 1,
    display_mode: displayMode as DisplayMode,
    sections: [{ key: null, title: null, allowed_types: blocks.question_types.map((q) => q.key).filter((k) => !excluded.includes(k)) }],
    parameters: [],
    lock_scope: [],
  };
}

export function templateHref(lang: string, area: TemplateArea, id: string): string {
  if (area.kind === "platform") return `/${lang}/admin/exam-templates/${id}`;
  if (area.kind === "org") return `/${lang}/org/${area.orgId}/exam-templates/${id}`;
  return `/${lang}/exam-templates/${id}`;
}

export function ExamTemplatesPage({ area, breadcrumbs }: { area: TemplateArea; breadcrumbs?: Breadcrumb[] }) {
  const { lang, t } = useTranslation();
  const [status, setStatus] = useState<"" | ExamTemplateStatus>("");
  const [scope, setScope] = useState<"" | ExamTemplateScope>("");
  const [creating, setCreating] = useState(false);
  const readOnly = area.kind === "org" && !!area.readOnly;

  const fetchPage = useCallback((cursor: string | null) => listExamTemplates({
    ...(area.kind === "teacher" ? { scope: "teacher" as const } : area.kind === "platform" ? (scope ? { scope } : {}) : { organization_id: area.orgId, ...(scope ? { scope } : {}) }),
    ...(status ? { status } : {}),
    cursor, limit: 50,
  }), [area, scope, status]);
  const list = useCursorList(fetchPage);
  const state = useTableState(list);

  const scopeOptions: ExamTemplateScope[] = area.kind === "platform" ? ["platform", "organization", "teacher"] : area.kind === "org" ? ["organization", "teacher"] : [];

  const columns: TableColumn<ExamTemplateOut>[] = [
    {
      key: "title", header: t("examTemplates.list.title"), primary: true,
      cell: (x) => (
        <Link href={templateHref(lang, area, x.id)} className="break-words font-semibold text-brand-700 hover:underline">
          {pickLocalized(x.title, lang) || t("examTemplates.untitled")}
        </Link>
      ),
    },
    { key: "scope", header: t("examTemplates.list.scope"), cell: (x) => <ScopeBadge scope={x.owner_scope} /> },
    { key: "status", header: t("examTemplates.list.status"), cell: (x) => <TemplateStatusBadge status={x.status} /> },
    { key: "version", header: t("examTemplates.list.version"), cell: (x) => x.current_version_no != null ? t("examTemplates.versionShort", { n: x.current_version_no }) : <span className="text-slate-500">—</span> },
    { key: "locked", header: t("examTemplates.list.locked"), cell: (x) => x.locked ? <LockedBadge /> : <span className="text-slate-500">—</span> },
    { key: "updated", header: t("examTemplates.list.updated"), hideOnMobile: true, nowrap: true, cell: (x) => fmtDateTime(x.updated_at) },
  ];

  const newButton = (
    <Button disabled={readOnly} leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />} onClick={() => setCreating(true)}>
      {t("examTemplates.list.new")}
    </Button>
  );
  const filtered = !!(status || scope);
  return (
    <div>
      <PageHeader title={t("examTemplates.list.pageTitle")} description={t(`examTemplates.list.intro.${area.kind}`)}
        breadcrumbs={breadcrumbs} primaryAction={newButton} />
      <Table
        caption={t("examTemplates.list.pageTitle")}
        columns={columns}
        rows={list.items}
        rowKey={(x) => x.id}
        {...state}
        search={
          <FilterBar canReset={filtered} onReset={() => { setStatus(""); setScope(""); }}>
            <Select label={t("examTemplates.list.status")} value={status} containerClassName="sm:w-48"
              onChange={(e) => setStatus(e.target.value as "" | ExamTemplateStatus)}
              options={[{ value: "", label: t("examTemplates.list.allStatuses") }, ...EXAM_TEMPLATE_STATUSES.map((s) => ({ value: s, label: t(`examTemplates.status.${s}`) }))]} />
            {scopeOptions.length > 0 && (
              <Select label={t("examTemplates.list.scope")} value={scope} containerClassName="sm:w-48"
                onChange={(e) => setScope(e.target.value as "" | ExamTemplateScope)}
                options={[{ value: "", label: t("examTemplates.list.allScopes") }, ...scopeOptions.map((s) => ({ value: s, label: t(`examTemplates.scope.${s}`) }))]} />
            )}
          </FilterBar>
        }
        empty={
          <EmptyState icon={<LayoutTemplate />} title={t(filtered ? "examTemplates.list.emptyFiltered" : "examTemplates.list.empty")}
            description={filtered ? undefined : t(`examTemplates.list.emptyHint.${area.kind}`)} />
        }
      />
      <MoreError list={list} />
      <NewTemplateDialog open={creating} area={area} onClose={() => setCreating(false)} />
    </div>
  );
}

function NewTemplateDialog({ open, area, onClose }: { open: boolean; area: TemplateArea; onClose: () => void }) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const uid = useId().replace(/:/g, "");
  const [title, setTitle] = useState<LocalizedText>({});
  const [orgs, setOrgs] = useState<MyOrganizationOut[] | null>(null);
  const [orgId, setOrgId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [touched, setTouched] = useState(false);
  // Phase 8b S4: display-mode starter choice, listed from the blocks catalog
  const [blocks, setBlocks] = useState<BlocksOut | null>(null);
  const [displayMode, setDisplayMode] = useState<string>(DEFAULT_DISPLAY_MODE);

  useEffect(() => {
    if (!open) return;
    setTitle({}); setError(null); setTouched(false); setBusy(false); setDisplayMode(DEFAULT_DISPLAY_MODE);
    let live = true;
    getExamTemplateBlocks().then((b) => { if (live) setBlocks(b); }).catch((e) => { if (live) setError(e); });
    const stop = () => { live = false; };
    if (area.kind !== "teacher") return stop;
    if (area.kind !== "teacher") return;
    let alive = true;
    setOrgs(null);
    listMyOrganizations()
      .then((rows) => {
        if (!alive) return;
        const active = rows.filter((o) => o.status === "active");
        setOrgs(active);
        setOrgId(active[0]?.id ?? "");
      })
      .catch((e) => { if (alive) { setOrgs([]); setError(e); } });
    return () => { alive = false; stop(); };
  }, [open, area.kind]);

  const scope: ExamTemplateScope = area.kind === "platform" ? "platform" : area.kind === "org" ? "organization" : "teacher";
  const organizationId = area.kind === "org" ? area.orgId : area.kind === "teacher" ? orgId : null;
  const cleaned = cleanLocalized(title, LMS_LANGS);
  const titleOk = Object.keys(cleaned).length > 0;
  const orgOk = scope === "platform" || !!organizationId;

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setTouched(true);
    if (!titleOk || !orgOk || !blocks) return;
    setBusy(true);
    setError(null);
    try {
      const out = await createExamTemplate({ owner_scope: scope, organization_id: organizationId, title: cleaned, draft_spec: starterSpec(blocks, displayMode) });
      router.push(templateHref(lang, area, out.id));
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  const formId = `${uid}-form`;
  return (
    <Dialog open={open} onClose={onClose} busy={busy} size="md" title={t("examTemplates.create.title")}
      description={t(`examTemplates.scopeHint.${scope}`)}
      footer={(
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>{t("ui.cancel")}</Button>
          <Button type="submit" form={formId} loading={busy} disabled={!blocks || (area.kind === "teacher" && orgs !== null && orgs.length === 0)}>{t("examTemplates.create.submit")}</Button>
        </>
      )}>
      <form id={formId} onSubmit={(e) => void submit(e)} className="space-y-4">
        <div>
          <LocalizedTextInput label={t("examTemplates.fields.title")} languages={LMS_LANGS} defaultLanguage={lang}
            value={title} onChange={setTitle} maxLength={200} required />
          {touched && !titleOk && <p className="mt-1 text-sm text-danger-700">{t("examTemplates.fields.titleRequired")}</p>}
        </div>
        {blocks && (
          <RadioCards legend={t("examTemplates.create.displayMode")} hint={t("examTemplates.create.displayModeHint")} value={displayMode}
            onChange={setDisplayMode} disabled={busy}
            options={blocks.display_modes.map((m) => ({ value: m, label: t(`examTemplates.blocks.displayModes.${m}`), description: t(`examTemplates.constructor.displayMode.body.${m}`) }))} />
        )}
        {area.kind === "teacher" && orgs && orgs.length > 1 && (
          <Select label={t("examTemplates.create.organization")} hint={t("examTemplates.create.organizationHint")} value={orgId}
            onChange={(e) => setOrgId(e.target.value)} options={orgs.map((o) => ({ value: o.id, label: o.name }))} />
        )}
        {area.kind === "teacher" && orgs && orgs.length === 0 && !error && (
          <p className="text-sm text-danger-700">{t("examTemplates.saveAs.noOrg")}</p>
        )}
        <ExamTemplateError error={error} />
      </form>
    </Dialog>
  );
}
