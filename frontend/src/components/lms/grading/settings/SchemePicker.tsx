"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { listSchemes } from "@/lib/lms/grading";
import type { Num, SchemeSummaryOut, SchemeVersionRef } from "@/lib/lms/gradingTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { inputCls } from "@/components/lms/content/ui";
import { fmtNum } from "../schemes/params";
import { SchemeError } from "../schemes/SchemeError";

const MAX_PAGES = 5;

/**
 * Picks a grading scheme version: system schemes and the teacher's own, each at its current version.
 * `value` is a scheme_version id; `current` is the already-saved reference so an older version stays selectable.
 */
export function SchemePicker({
  id, value, current, onChange, disabled, defaultLanguage,
}: {
  id: string;
  value: string | null;
  current: SchemeVersionRef | null;
  onChange: (versionId: string | null) => void;
  disabled?: boolean;
  defaultLanguage?: Lang;
}) {
  const { lang, t } = useTranslation();
  const [schemes, setSchemes] = useState<SchemeSummaryOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let off = false;
    (async () => {
      try {
        const all: SchemeSummaryOut[] = [];
        let cursor: string | null = null;
        for (let i = 0; i < MAX_PAGES; i++) {
          const page: { items: SchemeSummaryOut[]; next_cursor: string | null } = await listSchemes({ cursor, limit: 100, include_system: true });
          all.push(...page.items);
          cursor = page.next_cursor;
          if (!cursor) break;
        }
        if (!off) setSchemes(all.filter((s) => !s.deleted_at && s.current_version));
      } catch (e) {
        if (!off) { setError(e); setSchemes([]); }
      }
    })();
    return () => { off = true; };
  }, []);

  const name = (title: SchemeSummaryOut["title"]) => pickLocalized(title, lang, defaultLanguage);
  const scale = (min: Num | null | undefined, max: Num | null | undefined) =>
    fmtNum(min) && fmtNum(max) ? ` (${fmtNum(min)}-${fmtNum(max)})` : "";
  const list = schemes ?? [];
  const inList = list.some((s) => s.current_version?.id === value);
  const system = list.filter((s) => s.is_system);
  const mine = list.filter((s) => !s.is_system);
  const opt = (s: SchemeSummaryOut) => (
    <option key={s.id} value={s.current_version!.id}>
      {name(s.title)} - {t(`schemes.types.${s.type}`)}{scale(s.current_version!.scale_min, s.current_version!.scale_max)}
    </option>
  );

  return (
    <div>
      <select id={id} className={inputCls} disabled={disabled || schemes === null} value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}>
        <option value="">{t("grading.settings.noScheme")}</option>
        {value && !inList && current && current.id === value && (
          <option value={current.id}>
            {name(current.title)} v{current.version_no} - {t(`schemes.types.${current.type}`)}{scale(current.scale_min, current.scale_max)}
          </option>
        )}
        {system.length > 0 && <optgroup label={t("grading.settings.systemSchemes")}>{system.map(opt)}</optgroup>}
        {mine.length > 0 && <optgroup label={t("grading.settings.mySchemes")}>{mine.map(opt)}</optgroup>}
      </select>
      <SchemeError error={error} className="mt-2" />
    </div>
  );
}
