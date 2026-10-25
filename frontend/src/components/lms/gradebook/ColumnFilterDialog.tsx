"use client";

import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { Modal } from "@/components/lms/assessments/Modal";
import { btnPrimary, btnSecondary } from "@/components/lms/course/staffUi"; // Phase 6b S5c

export interface ColumnOption {
  id: string;
  title: string;
}

/** Choose which assessment columns the gradebook loads (sent as `assessment_ids`; empty = all). */
export function ColumnFilterDialog({
  open, options, selected, onApply, onClose,
}: {
  open: boolean;
  options: ColumnOption[];
  /** null = all columns */
  selected: string[] | null;
  onApply: (ids: string[] | null) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const wasOpen = useRef(false);
  // initialise only when the dialog opens (props may be re-created on every parent render)
  useEffect(() => {
    if (open && !wasOpen.current) setPicked(new Set(selected ?? options.map((o) => o.id)));
    wasOpen.current = open;
  }, [open, selected, options]);

  function toggle(id: string) {
    setPicked((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  function apply() {
    const ids = options.map((o) => o.id).filter((id) => picked.has(id));
    onApply(ids.length === 0 || ids.length === options.length ? null : ids);
  }

  return (
    <Modal open={open} title={t("gradebook.columns.title")} onClose={onClose}>
      <div className="space-y-3">
        <div className="flex flex-wrap gap-2 text-sm">
          <button type="button" onClick={() => setPicked(new Set(options.map((o) => o.id)))} className="font-medium text-brand-700 underline">
            {t("gradebook.columns.all")}
          </button>
          <button type="button" onClick={() => setPicked(new Set())} className="font-medium text-brand-700 underline">
            {t("gradebook.columns.none")}
          </button>
        </div>
        <ul className="max-h-80 space-y-1 overflow-y-auto">
          {options.map((o) => (
            <li key={o.id}>
              <label className="flex items-start gap-2 rounded-lg px-2 py-1.5 text-sm text-slate-800 hover:bg-slate-50">
                <input type="checkbox" className="mt-0.5" checked={picked.has(o.id)} onChange={() => toggle(o.id)} />
                <span className="min-w-0 break-words">{o.title}</span>
              </label>
            </li>
          ))}
        </ul>
        <p className="text-xs text-slate-500">{t("gradebook.columns.hint")}</p>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className={btnSecondary}>{t("lms.common.cancel")}</button>
          <button type="button" onClick={apply} className={btnPrimary}>{t("gradebook.columns.apply")}</button>
        </div>
      </div>
    </Modal>
  );
}
