"use client";

import React, { useState } from "react";
import { Button, Input } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";
import { deleteGoal, putGoal } from "@/lib/lms/progress";
import { useErrorText } from "@/components/lms/home/useErrorText";

/** Inline goal editor: a percent 1..100, saved on demand, removable. */
export function GoalInput({ courseId, value, onChange }: { courseId: string; value: number | null; onChange: (v: number | null) => void }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const [text, setText] = useState(value === null ? "" : String(value));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const n = Number(text);
  const valid = text.trim() !== "" && Number.isInteger(n) && n >= 1 && n <= 100;

  const save = async () => {
    if (!valid) { setError(t("progress.goal.invalid")); return; }
    setBusy(true);
    setError(null);
    try {
      const r = await putGoal(courseId, n);
      onChange(r.goal_percent);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const clear = async () => {
    setBusy(true);
    setError(null);
    try {
      await deleteGoal(courseId);
      setText("");
      onChange(null);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-end gap-2">
        <Input label={t("progress.goal.label")} containerClassName="w-28" inputMode="numeric" value={text}
          onChange={(e) => setText(e.target.value.replace(/[^0-9]/g, "").slice(0, 3))} placeholder="%" error={error ?? undefined} />
        <Button type="button" onClick={() => void save()} disabled={busy || text === (value === null ? "" : String(value))}>{t("progress.goal.save")}</Button>
        {value !== null && <Button type="button" variant="secondary" onClick={() => void clear()} disabled={busy}>{t("progress.goal.clear")}</Button>}
      </div>
    </div>
  );
}
