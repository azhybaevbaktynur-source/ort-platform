"use client";

// UX rework D (UR-4): the outline's in-place input: new module, rename, and an add at the end of a module (a title, plus a
// web address for a link and the kind for an assignment). Enter saves, Esc cancels; the buttons are there for phones.
import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { AssignmentKind } from "@/lib/lms/assignmentTypes";
import { Button, cn } from "@/components/ui";
import { fieldBase, fieldBorder } from "@/components/ui/utils";

export interface InlineValues {
  title: string;
  url: string;
  assignmentKind: AssignmentKind;
  /** F5c: the optional minutes field of a link ("" when empty). */
  minutes: string;
}

const field = (invalid: boolean) => cn(fieldBase, fieldBorder(invalid), "min-h-11 py-1 sm:min-h-9");

export function InlineForm({ label, initial = "", submitLabel, busy, error, url, minutes, assignmentKinds, onSubmit, onCancel, className }: {
  /** Accessible name and placeholder of the title field. */
  label: string;
  initial?: string;
  submitLabel: string;
  busy: boolean;
  error: string | null;
  /** A link also asks for its web address. */
  url?: { label: string };
  /** F5c (COURSE_LESSONS_DESIGN §6): a link also takes its duration in minutes (optional). */
  minutes?: { label: string };
  /** An assignment also asks for its kind (fixed once created). */
  assignmentKinds?: { label: string; options: { value: AssignmentKind; label: string }[] };
  onSubmit: (v: InlineValues) => void;
  onCancel: () => void;
  className?: string;
}) {
  const { t } = useTranslation();
  const [title, setTitle] = useState(initial);
  const [address, setAddress] = useState("");
  const [mins, setMins] = useState("");
  const [assignmentKind, setAssignmentKind] = useState<AssignmentKind>(assignmentKinds?.options[0]?.value ?? "text");
  const titleRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    titleRef.current?.focus();
    titleRef.current?.select();
  }, []);

  return (
    <form noValidate className={cn("flex flex-wrap items-center gap-2", className)}
      onSubmit={(e) => { e.preventDefault(); if (!busy) onSubmit({ title: title.trim(), url: address.trim(), assignmentKind, minutes: mins.trim() }); }}
      onKeyDown={(e) => { if (e.key === "Escape" && !busy) { e.preventDefault(); e.stopPropagation(); onCancel(); } }}>
      <input ref={titleRef} type="text" aria-label={label} placeholder={label} title={label} value={title} maxLength={200} disabled={busy}
        aria-invalid={error ? true : undefined} onChange={(e) => setTitle(e.target.value)} className={cn(field(!!error), "min-w-0 flex-1 basis-48")} />
      {url && (
        <input type="url" inputMode="url" aria-label={url.label} placeholder="https://" title={url.label} value={address} disabled={busy}
          onChange={(e) => setAddress(e.target.value)} className={cn(field(!!error), "min-w-0 flex-1 basis-48")} />
      )}
      {minutes && (
        <input type="number" inputMode="numeric" min={1} max={600} step={1} aria-label={minutes.label} placeholder={minutes.label} title={minutes.label}
          value={mins} disabled={busy} onChange={(e) => setMins(e.target.value)} className={cn(field(false), "w-full sm:w-40")} />
      )}
      {assignmentKinds && (
        <select aria-label={assignmentKinds.label} title={assignmentKinds.label} value={assignmentKind} disabled={busy}
          onChange={(e) => setAssignmentKind(e.target.value as AssignmentKind)} className={cn(field(false), "w-full sm:w-auto")}>
          {assignmentKinds.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      )}
      <div className="flex items-center gap-3">
        <Button type="submit" size="sm" loading={busy}>{submitLabel}</Button>
        <Button variant="link" size="sm" disabled={busy} onClick={onCancel}>{t("lms.common.cancel")}</Button>
      </div>
      {error && <p role="alert" className="w-full text-sm leading-5 text-danger-700">{error}</p>}
    </form>
  );
}
