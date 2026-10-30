"use client";

// Phase 9 S4: editor of one enrollment-form field (PHASE_9_DESIGN §2.4, §4.10, §6): type, label, help, required,
// PII category (required per field), choice options, number bounds, text length. Keys are generated, never typed.
import React from "react";
import { Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { OPTIONS_PER_FIELD_MAX, TEXT_LIMITS } from "@/lib/lms/enrollmentForms";
import type { FieldIn, FormFieldOption, FormFieldType, Lang, LocalizedText, PiiCategory } from "@/lib/lms/types";
import { Button, Checkbox, IconButton, Input, Select } from "@/components/ui";

export const FIELD_TYPES: FormFieldType[] = [
  "short_text", "long_text", "single_choice", "multi_choice", "number", "date", "email", "phone",
];
export const PII_CATEGORIES: PiiCategory[] = ["none", "contact", "personal"];
const CHOICE: FormFieldType[] = ["single_choice", "multi_choice"];

/** A sensible PII default per type (the teacher can change it). */
export function defaultPii(type: FormFieldType): PiiCategory {
  if (type === "email" || type === "phone") return "contact";
  if (type === "date" || type === "short_text" || type === "long_text") return "personal";
  return "none";
}

function nextOptionKey(options: FormFieldOption[]): string {
  const used = new Set(options.map((o) => o.key));
  for (let i = options.length + 1; ; i += 1) if (!used.has(`o${i}`)) return `o${i}`;
}

export function FieldEditor({
  field, onChange, languages, defaultLanguage, disabled, idPrefix,
}: {
  field: FieldIn;
  onChange: (f: FieldIn) => void;
  languages: Lang[];
  defaultLanguage: Lang;
  disabled?: boolean;
  idPrefix: string;
}) {
  const { t } = useTranslation();
  const set = (patch: Partial<FieldIn>) => onChange({ ...field, ...patch });
  const isChoice = CHOICE.includes(field.type);
  const isText = field.type === "short_text" || field.type === "long_text";
  const options = field.options ?? [];

  const changeType = (type: FormFieldType) => {
    const patch: Partial<FieldIn> = { type };
    if (CHOICE.includes(type)) {
      patch.options = options.length ? options : [
        { key: "o1", label: { [defaultLanguage]: "" } as LocalizedText },
        { key: "o2", label: { [defaultLanguage]: "" } as LocalizedText },
      ];
    } else {
      patch.options = null;
    }
    if (type !== "number") patch.bounds = null;
    if (type !== "short_text" && type !== "long_text") patch.max_len = null;
    if (field.pii_category === defaultPii(field.type)) patch.pii_category = defaultPii(type);
    onChange({ ...field, ...patch });
  };

  const setOption = (i: number, label: LocalizedText) =>
    set({ options: options.map((o, j) => (j === i ? { ...o, label } : o)) });

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Select id={`${idPrefix}-type`} label={t("enrollmentForm.field.type")} value={field.type} disabled={disabled}
          onChange={(e) => changeType(e.target.value as FormFieldType)}
          options={FIELD_TYPES.map((ft) => ({ value: ft, label: t(`enrollmentForm.types.${ft}`) }))} />
        <Select id={`${idPrefix}-pii`} label={t("enrollmentForm.field.pii")} value={field.pii_category} disabled={disabled}
          hint={t(`enrollmentForm.pii.${field.pii_category}Hint`)}
          onChange={(e) => set({ pii_category: e.target.value as PiiCategory })}
          options={PII_CATEGORIES.map((p) => ({ value: p, label: t(`enrollmentForm.pii.${p}`) }))} />
      </div>
      <LocalizedTextInput label={t("enrollmentForm.field.label")} languages={languages} defaultLanguage={defaultLanguage}
        value={field.label} onChange={(label) => set({ label })} maxLength={200} required disabled={disabled} />
      <LocalizedTextInput label={t("enrollmentForm.field.help")} languages={languages} defaultLanguage={defaultLanguage}
        value={field.help ?? {}} onChange={(help) => set({ help })} maxLength={500} disabled={disabled} />
      <Checkbox id={`${idPrefix}-required`} label={t("enrollmentForm.field.required")} checked={!!field.required}
        disabled={disabled} onChange={(e) => set({ required: e.target.checked })} />

      {isChoice && (
        <fieldset className="space-y-3">
          <legend className="mb-1 text-sm font-medium text-slate-700">{t("enrollmentForm.field.options")}</legend>
          {options.map((o, i) => (
            <div key={o.key} className="flex items-end gap-2">
              <div className="min-w-0 flex-1">
                <LocalizedTextInput label={t("enrollmentForm.field.option", { n: i + 1 })} languages={languages}
                  defaultLanguage={defaultLanguage} value={o.label} onChange={(label) => setOption(i, label)}
                  maxLength={200} required disabled={disabled} />
              </div>
              <IconButton aria-label={t("enrollmentForm.field.removeOption", { n: i + 1 })} icon={<Trash2 className="h-4 w-4" />}
                disabled={disabled || options.length <= 1} onClick={() => set({ options: options.filter((_, j) => j !== i) })} />
            </div>
          ))}
          <Button variant="secondary" size="sm" leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}
            disabled={disabled || options.length >= OPTIONS_PER_FIELD_MAX}
            onClick={() => set({ options: [...options, { key: nextOptionKey(options), label: { [defaultLanguage]: "" } as LocalizedText }] })}>
            {t("enrollmentForm.field.addOption")}
          </Button>
        </fieldset>
      )}

      {field.type === "number" && (
        <div className="grid gap-4 sm:grid-cols-2">
          {(["min", "max"] as const).map((k) => (
            <Input key={k} id={`${idPrefix}-${k}`} label={t(`enrollmentForm.field.${k}`)} optional type="text" inputMode="decimal"
              disabled={disabled} value={field.bounds?.[k] ?? ""}
              onChange={(e) => {
                const raw = e.target.value.trim().replace(",", ".");
                const n = raw === "" ? null : Number(raw);
                set({ bounds: { ...(field.bounds ?? {}), [k]: n === null || Number.isFinite(n) ? n : field.bounds?.[k] ?? null } });
              }} />
          ))}
        </div>
      )}

      {isText && (
        <Input id={`${idPrefix}-maxlen`} label={t("enrollmentForm.field.maxLen")} optional type="number" min={1}
          max={TEXT_LIMITS[field.type as "short_text" | "long_text"].max} disabled={disabled}
          hint={t("enrollmentForm.field.maxLenHint", { def: TEXT_LIMITS[field.type as "short_text" | "long_text"].def, max: TEXT_LIMITS[field.type as "short_text" | "long_text"].max })}
          value={field.max_len ?? ""}
          onChange={(e) => set({ max_len: e.target.value ? Math.max(1, parseInt(e.target.value, 10) || 1) : null })} />
      )}
    </div>
  );
}
