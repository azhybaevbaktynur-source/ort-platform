"use client";

import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { CategoryOut } from "@/lib/lms/gradingTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { Button, Checkbox, Dialog, Select } from "@/components/ui";
import { KindIcon } from "@/components/lms/assignments/assignmentUi";

export interface ColumnOption {
  id: string;
  title: string;
  /** Phase 7a S5: assignment kind and category (filter by kind / category) */
  kind?: "none" | "text" | "file" | "quiz";
  categoryId?: string | null;
}

type KindKey = NonNullable<ColumnOption["kind"]>;

/**
 * Choose which assignment columns the gradebook loads (sent as `assignment_ids`; empty = all).
 * Phase 7a S5: design-system Dialog; quick picks by kind and by category.
 */
export function ColumnFilterDialog({
  open, options, selected, categories = [], defaultLanguage, onApply, onClose,
}: {
  open: boolean;
  options: ColumnOption[];
  /** null = all columns */
  selected: string[] | null;
  categories?: CategoryOut[];
  defaultLanguage?: Lang;
  onApply: (ids: string[] | null) => void;
  onClose: () => void;
}) {
  const { lang, t } = useTranslation();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [kind, setKind] = useState<KindKey | "">("");
  const [category, setCategory] = useState("");
  const wasOpen = useRef(false);
  // initialise only when the dialog opens (props may be re-created on every parent render)
  useEffect(() => {
    if (open && !wasOpen.current) { setPicked(new Set(selected ?? options.map((o) => o.id))); setKind(""); setCategory(""); }
    wasOpen.current = open;
  }, [open, selected, options]);

  function toggle(id: string) {
    setPicked((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  /** Select exactly the columns that match the kind and category filters. */
  function pickMatching(k: KindKey | "", c: string) {
    setKind(k);
    setCategory(c);
    if (!k && !c) { setPicked(new Set(options.map((o) => o.id))); return; }
    setPicked(new Set(options.filter((o) => (!k || o.kind === k) && (!c || o.categoryId === c)).map((o) => o.id)));
  }

  function apply() {
    const ids = options.map((o) => o.id).filter((id) => picked.has(id));
    onApply(ids.length === 0 || ids.length === options.length ? null : ids);
  }

  const kinds = Array.from(new Set(options.map((o) => o.kind).filter(Boolean))) as KindKey[];
  return (
    <Dialog open={open} title={t("gradebook.columns.title")} description={t("gradebook.columns.hint")} onClose={onClose} size="md"
      footer={(
        <>
          <Button variant="secondary" onClick={onClose}>{t("ui.cancel")}</Button>
          <Button onClick={apply}>{t("gradebook.columns.apply")}</Button>
        </>
      )}>
      <div className="space-y-3">
        {(kinds.length > 1 || categories.length > 0) && (
          <div className="grid gap-3 sm:grid-cols-2">
            {kinds.length > 1 && (
              <Select label={t("assignments.list.filterKind")} value={kind} onChange={(e) => pickMatching(e.target.value as KindKey | "", category)}
                options={[{ value: "", label: t("assignments.list.allKinds") }, ...kinds.map((k) => ({ value: k, label: t(`assignments.kinds.${k}`) }))]} />
            )}
            {categories.length > 0 && (
              <Select label={t("assignments.list.filterCategory")} value={category} onChange={(e) => pickMatching(kind, e.target.value)}
                options={[{ value: "", label: t("assignments.list.allCategories") }, ...categories.map((c) => ({ value: c.id, label: pickLocalized(c.title, lang, defaultLanguage) || "—" }))]} />
            )}
          </div>
        )}
        <div className="flex flex-wrap gap-x-4">
          <Button variant="link" onClick={() => setPicked(new Set(options.map((o) => o.id)))}>{t("gradebook.columns.all")}</Button>
          <Button variant="link" onClick={() => setPicked(new Set())}>{t("gradebook.columns.none")}</Button>
        </div>
        <ul className="max-h-80 overflow-y-auto">
          {options.map((o) => (
            <li key={o.id}>
              <Checkbox checked={picked.has(o.id)} onChange={() => toggle(o.id)}
                label={<span className="inline-flex min-w-0 items-start gap-1.5">{o.kind && <KindIcon kind={o.kind} className="mt-1 h-4 w-4 text-slate-500" />}<span className="min-w-0 break-words">{o.title}</span></span>} />
            </li>
          ))}
        </ul>
      </div>
    </Dialog>
  );
}
