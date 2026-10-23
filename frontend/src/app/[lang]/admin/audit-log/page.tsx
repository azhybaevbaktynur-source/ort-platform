"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { listAuditLog } from "@/lib/lms/admin";
import type { AuditEntryOut } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Pager } from "@/components/lms/Pager";
import { AuditTable } from "@/components/lms/admin/AuditTable";

const TARGET_TYPES = ["", "user", "course", "teacher_request", "enrollment"];

export default function AuditLogPage() {
  const { t } = useTranslation();
  const [action, setAction] = useState("");
  const [actorId, setActorId] = useState("");
  const [targetType, setTargetType] = useState("");
  const [applied, setApplied] = useState({ action: "", actorId: "", targetType: "" });
  const [items, setItems] = useState<AuditEntryOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listAuditLog({ action: applied.action, actor_id: applied.actorId, target_type: applied.targetType, cursor: next });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [applied]);
  useEffect(() => { void load(); }, [load]);

  const field = "rounded-xl border border-slate-300 px-3 py-2 text-sm";
  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold text-slate-900">{t("platformAdmin.audit.title")}</h1>
      <form className="mb-4 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); setApplied({ action: action.trim(), actorId: actorId.trim(), targetType }); }}>
        <div>
          <label htmlFor="a-action" className="block text-xs font-medium text-slate-600">{t("platformAdmin.audit.action")}</label>
          <input id="a-action" value={action} onChange={(e) => setAction(e.target.value)} placeholder="course.delete" className={field} />
        </div>
        <div>
          <label htmlFor="a-actor" className="block text-xs font-medium text-slate-600">{t("platformAdmin.audit.actorId")}</label>
          <input id="a-actor" value={actorId} onChange={(e) => setActorId(e.target.value)} className={field} />
        </div>
        <div>
          <label htmlFor="a-type" className="block text-xs font-medium text-slate-600">{t("platformAdmin.audit.targetType")}</label>
          <select id="a-type" value={targetType} onChange={(e) => setTargetType(e.target.value)} className={field}>
            {TARGET_TYPES.map((x) => <option key={x} value={x}>{x ? t(`platformAdmin.audit.targetTypes.${x}`) : t("platformAdmin.audit.anyType")}</option>)}
          </select>
        </div>
        <button type="submit" className="rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700">{t("platformAdmin.audit.apply")}</button>
      </form>
      {error ? <ErrorMessage error={error} onRetry={() => load()} className="mb-4" /> : null}
      {loading && items.length === 0 && !error && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{t("platformAdmin.audit.empty")}</p>
      )}
      {items.length > 0 && <AuditTable entries={items} />}
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
    </div>
  );
}
