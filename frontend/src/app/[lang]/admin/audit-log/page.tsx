"use client";

import React, { useCallback, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { listAuditLog } from "@/lib/lms/admin";
import { Button, EmptyState, Input, PageHeader, STAFF_WIDTH, Select } from "@/components/ui";
import { AuditTable } from "@/components/lms/admin/AuditTable";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";

// Phase 7b S5: + every target type of the audit CHECK (organizations, invitations, exam templates, assessments)
const TARGET_TYPES = ["", "user", "course", "teacher_request", "enrollment", "organization", "invitation", "exam_template", "assessment"];

const ACTING_AS = ["", "org_admin", "platform_admin"] as const;
type ActingAs = (typeof ACTING_AS)[number];

export default function AuditLogPage() {
  const { t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const [action, setAction] = useState("");
  const [actorId, setActorId] = useState("");
  const [targetType, setTargetType] = useState("");
  const [actingAs, setActingAs] = useState<ActingAs>(""); // item 4: details.acting_as
  const [applied, setApplied] = useState<{ action: string; actorId: string; targetType: string; actingAs: ActingAs }>({ action: "", actorId: "", targetType: "", actingAs: "" });
  const fetchPage = useCallback(
    (cursor: string | null) => listAuditLog({
      action: applied.action, actor_id: applied.actorId, target_type: applied.targetType, acting_as: applied.actingAs, cursor,
    }),
    [applied],
  );
  const list = useCursorList(fetchPage);
  const state = useTableState(list);

  return (
    <div className={`w-full ${STAFF_WIDTH.list}`}>
      <PageHeader title={t("platformAdmin.audit.title")} description={t("platformAdmin.audit.subtitle")} breadcrumbs={crumbs({ label: t("platformAdmin.audit.title") })} />
      <form role="search" className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end"
        onSubmit={(e) => { e.preventDefault(); setApplied({ action: action.trim(), actorId: actorId.trim(), targetType, actingAs }); }}>
        <Input containerClassName="sm:w-56" label={t("platformAdmin.audit.action")} value={action} onChange={(e) => setAction(e.target.value)} placeholder="course.delete" />
        <Input containerClassName="sm:w-56" label={t("platformAdmin.audit.actorId")} value={actorId} onChange={(e) => setActorId(e.target.value)} />
        <Select containerClassName="sm:w-56" label={t("platformAdmin.audit.targetType")} value={targetType} onChange={(e) => setTargetType(e.target.value)}
          options={TARGET_TYPES.map((x) => ({ value: x, label: x ? t(`platformAdmin.audit.targetTypes.${x}`) : t("platformAdmin.audit.anyType") }))} />
        <Select containerClassName="sm:w-56" label={t("platformAdmin.audit.actingAsFilter")} value={actingAs} onChange={(e) => setActingAs(e.target.value as ActingAs)}
          options={ACTING_AS.map((x) => ({ value: x, label: x ? t(`platformAdmin.audit.actingAsOptions.${x}`) : t("platformAdmin.audit.actingAsAny") }))} />
        <Button type="submit" variant="secondary">{t("platformAdmin.audit.apply")}</Button>
      </form>
      <AuditTable entries={list.items} {...state} empty={<EmptyState title={t("platformAdmin.audit.empty")} />} />
      <MoreError list={list} />
    </div>
  );
}
