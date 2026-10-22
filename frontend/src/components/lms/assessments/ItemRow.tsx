"use client";

import React, { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, GripVertical } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { deleteItem, reorderItems, updateItem } from "@/lib/lms/assessments";
import type { ItemOut, SectionOut } from "@/lib/lms/assessmentTypes";
import { btnDanger, btnPrimary, btnSecondary, btnSmall } from "@/components/lms/content/ui";
import { Modal } from "./Modal";
import { PickFields, type PickValue } from "./PickFields";
import { AssessmentError } from "./AssessmentError";
import { fmtPoints, moveIndex } from "./format";

export interface RowCtx {
  courseId: string;
  assessmentId: string;
  canEdit: boolean;
  sections: SectionOut[];
  currentSectionId: string;
  onChanged: () => void | Promise<void>;
  onError: (e: unknown) => void;
}

/** One top-level or child item. Points edit inline on blur; move/delete go through the API then reload. */
export function ItemRow({
  item, ctx, index, count, onMoveBy, dragProps, childOf,
}: {
  item: ItemOut;
  ctx: RowCtx;
  index: number;
  count: number;
  onMoveBy: (delta: number) => void;
  dragProps?: React.HTMLAttributes<HTMLLIElement>;
  childOf?: string;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);
  const [points, setPoints] = useState(fmtPoints(item.points));
  const [pickEdit, setPickEdit] = useState<PickValue | null>(null);
  const [pickBusy, setPickBusy] = useState(false);
  const [pickError, setPickError] = useState<unknown>(null);
  useEffect(() => setPoints(fmtPoints(item.points)), [item.points]);

  const guard = async (fn: () => Promise<unknown>) => {
    try { await fn(); await ctx.onChanged(); } catch (e) { ctx.onError(e); await ctx.onChanged(); }
  };
  const savePoints = () => {
    if (points === fmtPoints(item.points)) return;
    const n = Number(points);
    if (!Number.isFinite(n) || n < 0 || n > 1000) { setPoints(fmtPoints(item.points)); return; }
    void guard(() => updateItem(ctx.courseId, ctx.assessmentId, item.id, { points: n }));
  };
  const savePick = async () => {
    if (!pickEdit) return;
    setPickBusy(true);
    setPickError(null);
    try {
      await updateItem(ctx.courseId, ctx.assessmentId, item.id, { pick: pickEdit });
      setPickEdit(null);
      await ctx.onChanged();
    } catch (e) {
      setPickError(e);
    } finally {
      setPickBusy(false);
    }
  };

  const moveChild = (i: number, delta: number) => {
    const ids = (item.children ?? []).map((c) => c.id);
    void guard(() => reorderItems(ctx.courseId, ctx.assessmentId, ctx.currentSectionId, { item_ids: moveIndex(ids, i, i + delta), parent_item_id: item.id }));
  };
  const q = item.question;
  const sectionLabel = (s: SectionOut) => s.key ? (t(`sections.${s.key}`) !== `sections.${s.key}` ? t(`sections.${s.key}`) : s.key) : t("assessments.section.n", { n: s.position });

  return (
    <li {...dragProps} className="rounded-xl border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2">
        {ctx.canEdit && !childOf && <GripVertical className="h-4 w-4 flex-shrink-0 cursor-grab text-slate-400" aria-hidden="true" />}
        {item.kind === "passage" && (
          <button type="button" aria-expanded={open} aria-label={open ? t("assessments.item.collapse") : t("assessments.item.expand")} onClick={() => setOpen((o) => !o)}>
            {open ? <ChevronDown className="h-4 w-4" aria-hidden="true" /> : <ChevronRight className="h-4 w-4" aria-hidden="true" />}
          </button>
        )}
        <div className="min-w-0 flex-1 text-sm">
          {item.kind === "question" && q && (
            <>
              <p className={`line-clamp-2 ${q.deleted ? "text-slate-400 line-through" : "text-slate-800"}`}>{q.stem_excerpt || t("assessments.add.noStem")}</p>
              <p className="text-xs text-slate-500">
                {t(`bank.types.${q.type}.name`)} · {q.language.toUpperCase()}
                {q.deleted && <span className="ml-2 font-semibold text-red-700">{t("assessments.item.deleted")}</span>}
                {q.newer_version_available && <span className="ml-2 font-semibold text-amber-700">{t("assessments.item.newerVersion")}</span>}
              </p>
            </>
          )}
          {item.kind === "passage" && (
            <p className="font-medium text-slate-800">
              {t("assessments.item.passage")}: {item.passage?.title || t("assessments.untitled")}
              <span className="ml-2 text-xs font-normal text-slate-500">{t("assessments.item.children", { n: item.children?.length ?? 0 })}</span>
            </p>
          )}
          {item.kind === "pick" && item.pick && (
            <>
              <p className="font-medium text-slate-800">{t("assessments.item.pick", { n: item.pick.count })}</p>
              <p className="text-xs text-slate-500">
                {Object.entries(item.pick.filter).filter(([, v]) => v && (!Array.isArray(v) || v.length)).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(",") : v}`).join(" · ") || t("assessments.item.noFilter")}
                {" · "}{t("assessments.item.pool")}: {Object.entries(item.pick.pool_size).map(([l, n]) => `${l.toUpperCase()} ${n}`).join(", ") || "0"}
              </p>
            </>
          )}
        </div>
        {item.kind !== "passage" && (
          <label className="flex items-center gap-1 text-xs text-slate-600">
            {t("assessments.item.points")}
            <input type="number" min={0} max={1000} step="any" className="w-16 rounded-lg border border-slate-300 px-2 py-1 text-sm" disabled={!ctx.canEdit}
              value={points} onChange={(e) => setPoints(e.target.value)} onBlur={savePoints} />
          </label>
        )}
        {ctx.canEdit && (
          <div className="flex flex-wrap items-center gap-1">
            <button type="button" className={btnSmall} disabled={index === 0} aria-label={t("assessments.item.up")} onClick={() => onMoveBy(-1)}><ArrowUp className="h-3.5 w-3.5" aria-hidden="true" /></button>
            <button type="button" className={btnSmall} disabled={index === count - 1} aria-label={t("assessments.item.down")} onClick={() => onMoveBy(1)}><ArrowDown className="h-3.5 w-3.5" aria-hidden="true" /></button>
            {item.kind === "pick" && item.pick && (
              <button type="button" className={btnSmall} onClick={() => { setPickError(null); setPickEdit({ bank_id: item.pick!.bank_id, count: item.pick!.count, filter: item.pick!.filter }); }}>{t("assessments.item.edit")}</button>
            )}
            {!childOf && ctx.sections.length > 1 && (
              <select aria-label={t("assessments.item.moveTo")} className="rounded-lg border border-slate-300 px-1.5 py-1 text-xs" value=""
                onChange={(e) => { const sid = e.target.value; if (sid) void guard(() => updateItem(ctx.courseId, ctx.assessmentId, item.id, { section_id: sid })); }}>
                <option value="">{t("assessments.item.moveTo")}</option>
                {ctx.sections.filter((s) => s.id !== ctx.currentSectionId).map((s) => <option key={s.id} value={s.id}>{sectionLabel(s)}</option>)}
              </select>
            )}
            <button type="button" className={btnDanger} onClick={() => void guard(() => deleteItem(ctx.courseId, ctx.assessmentId, item.id))}>{t("assessments.item.remove")}</button>
          </div>
        )}
      </div>
      {item.kind === "passage" && open && item.children && item.children.length > 0 && (
        <ul className="space-y-1 border-t border-slate-100 bg-slate-50/60 p-2 pl-6">
          {item.children.map((c, i) => (
            <ItemRow key={c.id} item={c} ctx={ctx} index={i} count={item.children!.length} childOf={item.id} onMoveBy={(d) => moveChild(i, d)} />
          ))}
        </ul>
      )}
      <Modal open={!!pickEdit} title={t("assessments.pick.editTitle")} onClose={() => setPickEdit(null)} busy={pickBusy}>
        {pickEdit && <PickFields courseId={ctx.courseId} value={pickEdit} onChange={setPickEdit} />}
        <AssessmentError error={pickError} className="mt-3" />
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className={btnSecondary} disabled={pickBusy} onClick={() => setPickEdit(null)}>{t("lms.common.cancel")}</button>
          <button type="button" className={btnPrimary} disabled={pickBusy} onClick={() => void savePick()}>{t("lms.common.save")}</button>
        </div>
      </Modal>
    </li>
  );
}
