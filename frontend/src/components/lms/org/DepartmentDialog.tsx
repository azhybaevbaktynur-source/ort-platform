"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import {
  SLUG_RE, createDepartment, slugify, updateDepartment, type DepartmentOut,
} from "@/lib/lms/organizations";
import { Button, Dialog, Input, Select } from "@/components/ui";
import { OrgError } from "./OrgUi";

export type DepartmentDialogMode =
  | { kind: "create"; parentId: string }
  | { kind: "rename"; dept: DepartmentOut }
  | { kind: "move"; dept: DepartmentOut };

const MAX_DEPTH = 2;

/** Height of the subtree under `dept` (0 for a leaf), from the loaded tree rows. */
function subtreeHeight(rows: DepartmentOut[], dept: DepartmentOut): number {
  const inside = rows.filter((r) => r.path === dept.path || r.path.startsWith(`${dept.path}/`));
  return Math.max(...inside.map((r) => r.depth)) - dept.depth;
}

/**
 * Phase 9 S2 (PHASE_9_DESIGN 4.1, 8.4): create, rename or move a department. Places offered for a move exclude
 * the department itself, its descendants and any place that would nest deeper than two levels (the server
 * refuses them too: `department_cycle`, `department_depth`).
 */
export function DepartmentDialog({ mode, orgId, rows, onClose, onDone }: {
  mode: DepartmentDialogMode | null;
  orgId: string;
  rows: DepartmentOut[];
  onClose: () => void;
  onDone: (kind: DepartmentDialogMode["kind"]) => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [parentId, setParentId] = useState("");
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!mode) return;
    setChecked(false);
    setError(null);
    setSlugTouched(false);
    if (mode.kind === "create") { setName(""); setSlug(""); setParentId(mode.parentId); }
    else { setName(mode.dept.name); setSlug(mode.dept.slug); setParentId(mode.dept.parent_id ?? ""); }
  }, [mode]);

  if (!mode) return null;
  const nameOk = name.trim().length > 0;
  const slugOk = SLUG_RE.test(slug);
  const indent = (r: DepartmentOut) => `${"  ".repeat(Math.max(0, r.depth - (rows[0]?.depth ?? 0)))}${r.name}`;
  const createParents = rows.filter((r) => r.depth < MAX_DEPTH);
  const moveParents = mode.kind === "move"
    ? rows.filter((r) => !(r.path === mode.dept.path || r.path.startsWith(`${mode.dept.path}/`))
      && r.depth + 1 + subtreeHeight(rows, mode.dept) <= MAX_DEPTH)
    : [];

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setChecked(true);
    if (mode.kind !== "move" && !nameOk) return;
    if (mode.kind === "create" && !slugOk) return;
    setBusy(true);
    setError(null);
    try {
      if (mode.kind === "create") await createDepartment(orgId, { name: name.trim(), slug, parent_id: parentId || null });
      else if (mode.kind === "rename") await updateDepartment(orgId, mode.dept.id, { name: name.trim() });
      else await updateDepartment(orgId, mode.dept.id, { parent_id: parentId });
      onDone(mode.kind);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const formId = "department-form";
  const title = t(mode.kind === "create" ? "departments.createTitle" : mode.kind === "rename" ? "departments.renameTitle" : "departments.moveTitle");
  return (
    <Dialog open title={title} onClose={onClose} busy={busy}
      description={mode.kind === "move" ? mode.dept.name : undefined}
      footer={
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>{t("departments.cancel")}</Button>
          <Button type="submit" form={formId} loading={busy}>
            {t(mode.kind === "create" ? "departments.submitCreate" : mode.kind === "move" ? "departments.move" : "departments.save")}
          </Button>
        </>
      }>
      <form id={formId} onSubmit={submit} noValidate className="space-y-4">
        {mode.kind !== "move" && (
          <Input label={t("departments.name")} value={name} maxLength={200} disabled={busy} autoFocus
            error={checked && !nameOk ? t("organizations.fields.nameMissing") : undefined}
            onChange={(e) => { setName(e.target.value); if (mode.kind === "create" && !slugTouched) setSlug(slugify(e.target.value)); }} />
        )}
        {mode.kind === "create" && (
          <Input label={t("departments.slug")} value={slug} maxLength={64} disabled={busy} className="font-mono"
            hint={checked && !slugOk ? undefined : t("departments.slugHint")}
            error={checked && !slugOk ? t("departments.slugHint") : undefined}
            onChange={(e) => { setSlugTouched(true); setSlug(e.target.value.toLowerCase()); }} />
        )}
        {mode.kind === "create" && createParents.length > 1 && (
          <Select label={t("departments.parent")} value={parentId} disabled={busy}
            options={createParents.map((r) => ({ value: r.id, label: indent(r) }))}
            onChange={(e) => setParentId(e.target.value)} />
        )}
        {mode.kind === "move" && (
          <Select label={t("departments.parent")} hint={t("departments.moveHint")} value={parentId} disabled={busy}
            options={moveParents.map((r) => ({ value: r.id, label: indent(r) }))}
            onChange={(e) => setParentId(e.target.value)} />
        )}
        <OrgError error={error} />
      </form>
    </Dialog>
  );
}
