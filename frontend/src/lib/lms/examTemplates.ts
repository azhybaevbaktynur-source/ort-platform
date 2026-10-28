// Phase 7b S4: exam template API client (PHASE_7B_DESIGN 9.1).
import { getAuthHeader } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";
import { LmsApiError, lmsFetch } from "./client";
import type { Lang, PageOut } from "./types";
import type { AssessmentStaffOut, Issue } from "./assessmentTypes";
import type {
  BlocksOut, ExamTemplateCreateIn, ExamTemplateListParams, ExamTemplateOut, ExamTemplatePatchIn, ExamTemplatePublishOut,
  ExamTemplateVersionOut, ImportFormatOut, PreviewIn, PreviewOut, SandboxIn, SandboxOut, SaveAsTemplateIn, SpecDiffEnd, SpecDiffOut,
} from "./examTemplateTypes";
import type { BlockNavigation, BlockQuestionType, DisplayMode } from "./blocks";

const e = encodeURIComponent;
const base = "/exam-templates";
const one = (id: string) => `${base}/${e(id)}`;

/** Management mode without `course_id`; picker mode (published, visible in that course) with it. */
export const listExamTemplates = (p: ExamTemplateListParams = {}) =>
  lmsFetch<PageOut<ExamTemplateOut>>(base, { params: { ...p } });
export const getExamTemplateBlocks = () => lmsFetch<BlocksOut>(`${base}/blocks`);
export const createExamTemplate = (body: ExamTemplateCreateIn) => lmsFetch<ExamTemplateOut>(base, { method: "POST", body });
export const getExamTemplate = (id: string) => lmsFetch<ExamTemplateOut>(one(id));
export const patchExamTemplate = (id: string, body: ExamTemplatePatchIn) =>
  lmsFetch<ExamTemplateOut>(one(id), { method: "PATCH", body });
/** Returns `{template, version, unchanged}` (S5: the backend shape; `unchanged` = identical draft, no new version). */
export const publishExamTemplate = (id: string) => lmsFetch<ExamTemplatePublishOut>(`${one(id)}/publish`, { method: "POST", body: {} });
export const archiveExamTemplate = (id: string) => lmsFetch<ExamTemplateOut>(`${one(id)}/archive`, { method: "POST", body: {} });
export const lockExamTemplate = (id: string, reason: string) =>
  lmsFetch<ExamTemplateOut>(`${one(id)}/lock`, { method: "POST", body: reason ? { reason } : {} });
export const unlockExamTemplate = (id: string, reason: string) =>
  lmsFetch<ExamTemplateOut>(`${one(id)}/unlock`, { method: "POST", body: reason ? { reason } : {} });
export const promoteExamTemplate = (id: string) => lmsFetch<ExamTemplateOut>(`${one(id)}/promote`, { method: "POST", body: {} });

/** The backend returns every version as a plain list (newest first); wrapped as one page for the cursor lists. */
export const listExamTemplateVersions = (id: string): Promise<PageOut<ExamTemplateVersionOut>> =>
  lmsFetch<ExamTemplateVersionOut[]>(`${one(id)}/versions`).then((items) => ({ items, next_cursor: null }));
export const getExamTemplateVersion = (id: string, versionNo: number) =>
  lmsFetch<ExamTemplateVersionOut>(`${one(id)}/versions/${e(String(versionNo))}`);
export const getImportFormat = (id: string, versionNo: number) =>
  lmsFetch<ImportFormatOut>(`${one(id)}/versions/${e(String(versionNo))}/import-format`);

/**
 * `?download=csv&lang=`: the server sends `text/csv` with a BOM. Fetched with the auth header and saved through a
 * blob link (a plain `<a href>` would not carry the token).
 */
export async function downloadImportFormat(id: string, versionNo: number, lang: Lang): Promise<void> {
  const url = `${API_BASE_URL}${one(id)}/versions/${e(String(versionNo))}/import-format?download=csv&lang=${e(lang)}`;
  let res: Response;
  try {
    res = await fetch(url, { headers: { ...(await getAuthHeader()) }, cache: "no-store" });
  } catch {
    throw new LmsApiError(0, "network", "Network error");
  }
  if (!res.ok) {
    let data: unknown = undefined;
    try { data = JSON.parse(await res.text()); } catch { data = undefined; }
    const err = (data as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | undefined)?.error;
    if (err && typeof err.code === "string") throw new LmsApiError(res.status, err.code, err.message || err.code, err.details || {});
    throw new LmsApiError(res.status, res.status === 404 ? "not_found" : res.status === 403 ? "forbidden" : "unknown", `HTTP ${res.status}`);
  }
  const disposition = res.headers.get("content-disposition") || "";
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  const filename = m ? decodeURIComponent(m[1]) : `import-format-v${versionNo}.csv`;
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.rel = "noopener";
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 60_000);
}

// ---- Assessment-bound routes (assessments/router.py, S2 block) ----
const asm = (courseId: string, aid: string) => `/courses/${e(courseId)}/assessments/${e(aid)}`;

export const saveAsTemplate = (courseId: string, assessmentId: string, body: SaveAsTemplateIn) =>
  lmsFetch<ExamTemplateOut>(`${asm(courseId, assessmentId)}/save-as-template`, { method: "POST", body });

/** Upgrade a draft without attempts to the template's latest version; rules violations come back as issues. */
export interface TemplateUpgradeOut {
  assessment: AssessmentStaffOut;
  issues: Issue[];
}
export const upgradeAssessmentTemplate = (courseId: string, assessmentId: string) =>
  lmsFetch<TemplateUpgradeOut>(`${asm(courseId, assessmentId)}/template-upgrade`, { method: "POST", body: {} });
export const unlockAssessmentStructure = (courseId: string, assessmentId: string) =>
  lmsFetch<AssessmentStaffOut>(`${asm(courseId, assessmentId)}/structure-unlock`, { method: "POST", body: {} });

// --- Phase 8b S4 begin --- (PHASE_8B_DESIGN 6.1, 7, 9: sandbox, preview, diff; constructor constants)
/** Ensure (and sync from the stored draft) the template's sandbox course + sample quiz; idempotent, no attempt. */
export const ensureTemplateSandbox = (id: string, body: SandboxIn = {}) =>
  lmsFetch<SandboxOut>(`${one(id)}/sandbox`, { method: "POST", body });
/** Start a staff preview attempt of the sample quiz in the real player. */
export const startTemplatePreview = (id: string, body: PreviewIn = {}) =>
  lmsFetch<PreviewOut>(`${one(id)}/preview`, { method: "POST", body });
/** Computed diff between two versions, or a version and the draft (`to = "draft"`, managers only). */
export const getTemplateDiff = (id: string, from: SpecDiffEnd, to: SpecDiffEnd) =>
  lmsFetch<SpecDiffOut>(`${one(id)}/diff`, { params: { from: String(from), to: String(to) } });

/**
 * The few block keys the constructor reasons about (it never lists them: every pick list comes from
 * `GET /exam-templates/blocks`). Kept here, typed against `blocks.ts`, so `components/lms/examTemplates/**` holds no
 * literal block key (`backend/tests/lms/test_constructor_blocks_contract.py`). The values equal the server defaults.
 */
export const DEFAULT_NAVIGATION: BlockNavigation = "free";
export const FORWARD_ONLY_NAVIGATION: BlockNavigation = "section_forward_only";
export const DEFAULT_DISPLAY_MODE: DisplayMode = "one_per_page";
/** Types a new section leaves unchecked (ORT's comparison type; the author can still tick it). */
export const NEW_SECTION_EXCLUDED_TYPES: readonly BlockQuestionType[] = ["comparison"];

/** sessionStorage key of the constructor's crash-safety mirror (PHASE_8B_DESIGN 9.2). */
export const templateDraftStorageKey = (id: string) => `examTemplateDraft:${id}`;
// --- Phase 8b S4 end ---
