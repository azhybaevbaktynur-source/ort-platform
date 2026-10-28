"use client";

// Phase 8b S4: Versions tab (PHASE_8B_DESIGN 9.1): published versions with the import-format download and
// "Compare with previous" / "Compare with draft" opening the computed `DiffView`.
import React, { useCallback, useEffect, useState } from "react";
import { Download, GitCompare } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { downloadImportFormat, listExamTemplateVersions } from "@/lib/lms/examTemplates";
import type { BlocksOut, ExamTemplateOut, ExamTemplateVersionOut, SpecDiffEnd } from "@/lib/lms/examTemplateTypes";
import type { Lang } from "@/lib/lms/types";
import { fmtDateTime } from "@/components/lms/assessments/format";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { Button, Table, toast, type TableColumn } from "@/components/ui";
import { DiffView } from "./DiffView";
import { schemeTitle } from "./ScoringTab";
import { useExamTemplateErrorText } from "./ui";

export function VersionsTab({ tpl, blocks, canDiffDraft, reloadKey }: {
  tpl: ExamTemplateOut;
  blocks: BlocksOut | null;
  /** The caller manages the template and a stored draft exists (`to=draft`). */
  canDiffDraft: boolean;
  /** Changes after a publish so the list reloads. */
  reloadKey: number;
}) {
  const { lang, t } = useTranslation();
  const fetchVersions = useCallback(() => listExamTemplateVersions(tpl.id), [tpl.id]);
  const versions = useCursorList(fetchVersions);
  const vState = useTableState(versions);
  const [compare, setCompare] = useState<{ from: SpecDiffEnd; to: SpecDiffEnd } | null>(null);
  const { reload } = versions;
  useEffect(() => { if (reloadKey) void reload(); }, [reloadKey, reload]);

  const open = (from: SpecDiffEnd, to: SpecDiffEnd) => {
    setCompare({ from, to });
    requestAnimationFrame(() => document.getElementById("tpl-diff")?.scrollIntoView({ block: "start", behavior: "smooth" }));
  };
  const nos = versions.items.map((v) => v.version_no);
  const previousOf = (no: number) => nos.filter((n) => n < no).sort((a, b) => b - a)[0];

  const columns: TableColumn<ExamTemplateVersionOut>[] = [
    { key: "no", header: t("examTemplates.versions.version"), primary: true, cell: (v) => <span className="font-semibold">{t("examTemplates.versionShort", { n: v.version_no })}</span> },
    { key: "published", header: t("examTemplates.versions.published"), nowrap: true, cell: (v) => fmtDateTime(v.published_at) },
    {
      key: "scheme", header: t("examTemplates.editor.scheme"), hideOnMobile: true, cell: (v) => {
        if (!v.grading_scheme_version_id) return <span className="text-slate-600">{t("examTemplates.constructor.scoring.noScheme")}</span>;
        const b = blocks?.scheme_versions.find((s) => s.id === v.grading_scheme_version_id);
        return b ? schemeTitle(b, lang as Lang) : <span className="text-slate-600">{t("examTemplates.diff.otherScheme")}</span>;
      },
    },
    { key: "sections", header: t("examTemplates.versions.sections"), align: "right", cell: (v) => v.spec?.sections?.length ?? "—" },
    {
      key: "actions", header: t("examTemplates.constructor.versions.actions"), actions: true, cell: (v) => {
        const prev = previousOf(v.version_no);
        return (
          <div className="flex flex-wrap justify-end gap-2">
            <ImportFormatButton templateId={tpl.id} versionNo={v.version_no} />
            {prev !== undefined && (
              <Button variant="secondary" size="sm" leftIcon={<GitCompare className="h-4 w-4" aria-hidden="true" />}
                aria-label={t("examTemplates.diff.compareWithPreviousN", { n: v.version_no })} onClick={() => open(prev, v.version_no)}>
                {t("examTemplates.diff.compareWithPrevious")}
              </Button>
            )}
            {canDiffDraft && (
              <Button variant="secondary" size="sm" leftIcon={<GitCompare className="h-4 w-4" aria-hidden="true" />}
                aria-label={t("examTemplates.diff.compareWithDraftN", { n: v.version_no })} onClick={() => open(v.version_no, "draft")}>
                {t("examTemplates.diff.compareWithDraft")}
              </Button>
            )}
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">{t("examTemplates.importFormat.help")}</p>
      <Table caption={t("examTemplates.versions.title")} columns={columns} rows={versions.items} rowKey={(v) => v.id} {...vState}
        empty={<p className="px-4 py-6 text-center text-sm text-slate-600">{t("examTemplates.versions.empty")}</p>} />
      <MoreError list={versions} />
      {compare && <DiffView templateId={tpl.id} from={compare.from} to={compare.to} blocks={blocks} onClose={() => setCompare(null)} />}
    </div>
  );
}

export function ImportFormatButton({ templateId, versionNo }: { templateId: string; versionNo: number }) {
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
