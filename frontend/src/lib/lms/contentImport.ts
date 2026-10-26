import { getAuthHeader } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";
import { LmsApiError } from "./client";
import type { Lang } from "./types";


/** Limits shown in the UI; the server enforces them (design P2-22). */
export const IMPORT_LIMITS = { uploadMb: 50, rows: 5000, images: 1000 } as const;

export type ImportExamType = "full_main" | "subject" | "practice_bank";
export type ImportConflictPolicy = "skip" | "overwrite";

export interface ImportIssue {
  severity: "error" | "warning";
  code: string;
  message: string;
  bundle?: string | null;
  file?: string | null;
  row?: number | null;
  column?: string | null;
  params?: Record<string, unknown>;
}

export interface ImportBankSummary {
  root: string;
  source_id: string | null;
  has_manifest: boolean;
  language: string;
  bank_id: string | null;
  bank_title: string;
  bank_exists: boolean;
  question_count: number;
  sections: Record<string, number>;
  created: Record<string, number>;
  updated: Record<string, number>;
  unchanged: Record<string, number>;
  conflicts: Record<string, number>;
  skipped_deleted: Record<string, number>;
  images: number;
}

// --- Phase 7b S5 --- (`ImportResult.attached` of the backend: the commit-only attach step)
export interface ImportAttachSummary {
  assessment_id: string;
  added: number;
  /** section label -> questions added */
  sections: Record<string, number>;
  /** skip code (item_duplicate, too_many_items, ...) -> count */
  skipped: Record<string, number>;
}

export interface ImportReport {
  ok: boolean;
  committed: boolean;
  banks: ImportBankSummary[];
  errors: ImportIssue[];
  warnings: ImportIssue[];
  images_total: number;
  images_new: number;
  images_existing: number;
  attached?: ImportAttachSummary | null; // Phase 7b S5
}

export interface ImportParams {
  file: File;
  language: Lang;
  /** Empty/undefined = general mode; set = ORT preset. */
  examType?: ImportExamType | null;
  /** Only for a CSV or a single bundle without manifest; empty = new bank. */
  targetBankId?: string | null;
  onConflict?: ImportConflictPolicy;
  // --- Phase 7b S4 begin --- (PHASE_7B_DESIGN 8: validation against a template exam, general format only)
  /** Validate rows against the template version of this draft assessment (`not_a_template_assessment` otherwise). */
  assessmentId?: string | null;
  /** Validate against an explicit template version (no assessment). */
  examTemplateVersionId?: string | null;
  /** Commit only: add the imported questions to the sections of this draft assessment (same transaction). */
  attachToAssessmentId?: string | null;
  // --- Phase 7b S4 end ---
}

async function post(path: string, p: ImportParams, commit: boolean): Promise<ImportReport> {
  const form = new FormData();
  form.append("file", p.file);
  form.append("language", p.language);
  if (p.examType) form.append("exam_type", p.examType);
  if (p.targetBankId) form.append("target_bank_id", p.targetBankId);
  if (commit) form.append("on_conflict", p.onConflict ?? "skip");
  // --- Phase 7b S4 begin ---
  if (p.assessmentId) form.append("assessment_id", p.assessmentId);
  if (p.examTemplateVersionId) form.append("exam_template_version_id", p.examTemplateVersionId);
  if (commit && p.attachToAssessmentId) form.append("attach_to_assessment_id", p.attachToAssessmentId);
  // --- Phase 7b S4 end ---
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { ...(await getAuthHeader()) },
      body: form,
      cache: "no-store",
    });
  } catch {
    throw new LmsApiError(0, "network", "Network error");
  }
  const text = await res.text();
  let data: unknown = undefined;
  if (text) {
    try { data = JSON.parse(text); } catch { data = undefined; }
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | undefined)?.error;
    if (err && typeof err === "object" && typeof err.code === "string") {
      throw new LmsApiError(res.status, err.code, err.message || err.code, err.details || {});
    }
    const code = res.status === 413 ? "file_too_large" : res.status === 429 ? "rate_limited" : res.status === 403 ? "forbidden" : res.status === 404 ? "not_found" : "unknown";
    throw new LmsApiError(res.status, code, `HTTP ${res.status}`);
  }
  return data as ImportReport;
}

/** Dry run: validates everything, saves nothing. */
export const previewImport = (courseId: string, p: ImportParams) => post(`/courses/${courseId}/imports/preview`, p, false);
/** Commit: re-validates; any error means nothing is saved (report.committed false). */
export const commitImport = (courseId: string, p: ImportParams) => post(`/courses/${courseId}/imports`, p, true);
