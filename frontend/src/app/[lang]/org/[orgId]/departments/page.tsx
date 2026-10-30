"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { deleteDepartment, listDepartments, type DepartmentOut } from "@/lib/lms/organizations";
import { Button, ConfirmDialog, EmptyState, LoadingState, PageHeader, toast } from "@/components/ui";
import { useOrg } from "@/components/lms/org/OrgShell";
import { DepartmentDialog, type DepartmentDialogMode } from "@/components/lms/org/DepartmentDialog";
import { DepartmentTree, type DepartmentAction } from "@/components/lms/org/DepartmentTree";
import { LoadError, OrgError } from "@/components/lms/org/OrgUi";

/** Phase 9 S2 (PHASE_9_DESIGN 4.1, 8.1): the department tree of the organization (or of a department). */
export default function OrgDepartmentsPage() {
  const { t } = useTranslation();
  const { org, readOnly, crumbs, reload } = useOrg();
  const [rows, setRows] = useState<DepartmentOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [dialog, setDialog] = useState<DepartmentDialogMode | null>(null);
  const [toDelete, setToDelete] = useState<DepartmentOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setRows(await listDepartments(org.id));
    } catch (e) {
      setError(e);
    }
  }, [org.id]);
  useEffect(() => { void load(); }, [load]);

  const personal = org.kind === "personal";
  const canCreate = !readOnly && !personal && org.depth < 2;
  const onAction = (action: DepartmentAction, d: DepartmentOut) => {
    if (action === "create") setDialog({ kind: "create", parentId: d.id });
    else if (action === "rename") setDialog({ kind: "rename", dept: d });
    else if (action === "move") setDialog({ kind: "move", dept: d });
    else { setDeleteError(null); setToDelete(d); }
  };
  const remove = async () => {
    if (!toDelete) return;
    setBusy(true);
    setDeleteError(null);
    try {
      await deleteDepartment(org.id, toDelete.id);
      setToDelete(null);
      toast.success(t("departments.deleted"));
      await load();
      void reload();
    } catch (e) {
      setDeleteError(e);
    } finally {
      setBusy(false);
    }
  };

  const createButton = (variant: "primary" | "secondary") => (
    <Button variant={variant} disabled={!canCreate} leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />}
      onClick={() => setDialog({ kind: "create", parentId: org.id })}>{t("departments.create")}</Button>
  );
  return (
    <div>
      <PageHeader title={t("departments.title")} description={t("departments.intro")}
        breadcrumbs={crumbs({ label: t("departments.nav") })} primaryAction={personal ? undefined : createButton("primary")} />
      {error && !rows ? <LoadError error={error} onRetry={load} /> : !rows ? <LoadingState label={t("lms.common.loading")} /> : (
        <>
          <DepartmentTree rows={rows} readOnly={readOnly || personal} onAction={onAction} />
          {rows.length <= 1 && (
            <EmptyState className="mt-4" title={t("departments.empty")} description={t("departments.emptyHint")}
              action={canCreate ? createButton("secondary") : undefined} />
          )}
        </>
      )}
      <DepartmentDialog mode={dialog} orgId={org.id} rows={rows ?? []} onClose={() => setDialog(null)}
        onDone={(kind) => {
          setDialog(null);
          toast.success(t(kind === "create" ? "departments.created" : "departments.saved"));
          void load();
        }} />
      <ConfirmDialog open={!!toDelete} tone="danger" busy={busy} title={t("departments.deleteTitle")} object={toDelete?.name}
        effect={t("departments.deleteBody")} confirmLabel={t("departments.delete")} onConfirm={() => void remove()}
        onCancel={() => setToDelete(null)} error={deleteError ? <OrgError error={deleteError} /> : undefined} />
    </div>
  );
}
