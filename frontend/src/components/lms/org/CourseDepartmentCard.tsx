"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { listDepartments, moveOrgCourse, type DepartmentOut } from "@/lib/lms/organizations";
import { Button, Card, Select, toast } from "@/components/ui";
import { OrgError } from "./OrgUi";

/**
 * Phase 9 S5 (PHASE_9_DESIGN 4.1): the department of a course on the org admin course summary. Lists the
 * organizations of the tree (the organization itself first, departments indented) and moves the course with
 * PATCH /org/{orgId}/courses/{courseId}. Hidden while the organization has no departments. The roster is untouched.
 */
export function CourseDepartmentCard({ orgId, courseId, current, readOnly, onMoved }: {
  orgId: string;
  courseId: string;
  current: string;
  readOnly: boolean;
  onMoved: () => void;
}) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<DepartmentOut[] | null>(null);
  const [target, setTarget] = useState(current);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    try {
      setRows(await listDepartments(orgId));
    } catch {
      setRows([]);
    }
  }, [orgId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setTarget(current); }, [current]);

  if (!rows || rows.length <= 1) return null;
  const top = rows[0].depth;
  const options = rows.map((r) => ({ value: r.id, label: `${"  ".repeat(Math.max(0, r.depth - top))}${r.name}` }));
  // a course outside the listed subtree still shows where it is
  if (!rows.some((r) => r.id === current)) options.unshift({ value: current, label: "—" });

  const move = async () => {
    setBusy(true);
    setError(null);
    try {
      await moveOrgCourse(orgId, courseId, target);
      toast.success(t("departments.courseMoved", { name: rows.find((r) => r.id === target)?.name ?? "" }));
      onMoved();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title={t("departments.courseDepartment")} description={t("departments.courseDepartmentHint")}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="min-w-0 flex-1">
          <Select id="course-department" label={t("departments.usageDepartment")} value={target}
            disabled={busy || readOnly} options={options} onChange={(e) => setTarget(e.target.value)} />
        </div>
        <Button variant="secondary" loading={busy} disabled={readOnly || target === current} onClick={() => void move()}>
          {t("departments.moveCourse")}
        </Button>
      </div>
      {error ? <div className="mt-3"><OrgError error={error} /></div> : null}
    </Card>
  );
}
