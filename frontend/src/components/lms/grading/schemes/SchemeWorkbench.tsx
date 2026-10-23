"use client";

import React, { useMemo } from "react";
import type { SchemeParams, SchemeType } from "@/lib/lms/gradingTypes";
import { ParamIssues, SchemeParamsEditor } from "./SchemeParamsEditor";
import { SchemePreview } from "./SchemePreview";
import { cleanParams, type ParamIssue } from "./params";

/** Editor (left) and live preview (right; below on phones). Parents own the params and the issue list. */
export function SchemeWorkbench({
  type, params, onChange, issues, readOnly,
}: {
  type: SchemeType;
  params: SchemeParams;
  onChange: (p: SchemeParams) => void;
  issues: ParamIssue[];
  readOnly: boolean;
}) {
  const cleaned = useMemo(() => cleanParams(type, params), [type, params]);
  const expected = type === "lookup_table" ? (params as { expected_possible?: number | null }).expected_possible ?? null : null;
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
      <div className="min-w-0 space-y-4">
        <SchemeParamsEditor type={type} params={params} onChange={onChange} readOnly={readOnly} />
        {!readOnly && <ParamIssues issues={issues} />}
      </div>
      <div className="min-w-0 lg:sticky lg:top-4 lg:self-start">
        <SchemePreview type={type} params={cleaned} blocked={issues.length > 0} defaultPossible={expected && expected > 0 ? expected : null} />
      </div>
    </div>
  );
}
