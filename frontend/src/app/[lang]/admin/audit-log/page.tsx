"use client";

import React, { useCallback, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { listAuditLog } from "@/lib/lms/admin";
import { Button, EmptyState, Input, PageHeader, Select } from "@/components/ui";
import { AuditTable } from "@/components/lms/admin/AuditTable";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";

const TARGET_TYPES = ["", "user", "course", "teacher_request", "enrollment"];

export default function AuditLogPage() {
  const { t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const [action, setAction] = useState("");
  const [actorId, setActorId] = useState("");
  const [targetType, setTargetType] = useState("");
  const [applied, setApplied] = useState({ action: "", actorId: "", targetType: "" });
  const fetchPage = useCallback(
    (cursor: string | null) => listAuditLog({ action: applied.action, actor_id: applied.actorId, target_type: applied.targetType, cursor }),
    [applied],
  );
  const list = useCursorList(fetchPage);
  const state = useTableState(list);

  return (
    <div>
      <PageHeader title={t("platformAdmin.audit.title")} breadcrumbs={crumbs({ label: t("platformAdmin.audit.title") })} />
      <form role="search" className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end"
        onSubmit={(e) => { e.preventDefault(); setApplied({ action: action.trim(), actorId: actorId.trim(), targetType }); }}>
        <Input containerClassName="sm:w-56" label={t("platformAdmin.audit.action")} value={action} onChange={(e) => setAction(e.target.value)} placeholder="course.delete" />
        <Input containerClassName="sm:w-56" label={t("platformAdmin.audit.actorId")} value={actorId} onChange={(e) => setActorId(e.target.value)} />
        <Select containerClassName="sm:w-56" label={t("platformAdmin.audit.targetType")} value={targetType} onChange={(e) => setTargetType(e.target.value)}
          options={TARGET_TYPES.map((x) => ({ value: x, label: x ? t(`platformAdmin.audit.targetTypes.${x}`) : t("platformAdmin.audit.anyType") }))} />
        <Button type="submit" variant="secondary">{t("platformAdmin.audit.apply")}</Button>
      </form>
      <AuditTable entries={list.items} {...state} empty={<EmptyState title={t("platformAdmin.audit.empty")} />} />
      <MoreError list={list} />
    </div>
  );
}
