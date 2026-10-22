import { lmsFetch } from "./client";
import type { PageOut } from "./types";
import type {
  AssessmentCreateIn, AssessmentDetailOut, AssessmentStaffOut, AssessmentSummaryOut, AssessmentUpdateIn,
  BulkAddIn, BulkAddOut, ItemCreateIn, ItemOut, ItemUpdateIn, ItemsOrderIn, PreviewStartOut, PublishOut,
  SectionIn, SectionOut, ValidationOut, VersionOut,
} from "./assessmentTypes";
import type { Lang } from "./types";

const e = encodeURIComponent;
const a = (courseId: string) => `/courses/${e(courseId)}/assessments`;
const one = (courseId: string, id: string) => `${a(courseId)}/${e(id)}`;

export const listAssessments = (courseId: string, opts: { deleted?: boolean; cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<AssessmentSummaryOut>>(a(courseId), { params: { deleted: opts.deleted, cursor: opts.cursor, limit: opts.limit } });
export const createAssessment = (courseId: string, body: AssessmentCreateIn) =>
  lmsFetch<AssessmentStaffOut>(a(courseId), { method: "POST", body });
export const getAssessment = (courseId: string, id: string) => lmsFetch<AssessmentDetailOut>(one(courseId, id));
export const updateAssessment = (courseId: string, id: string, body: AssessmentUpdateIn) =>
  lmsFetch<AssessmentStaffOut>(one(courseId, id), { method: "PATCH", body });
export const deleteAssessment = (courseId: string, id: string) => lmsFetch<void>(one(courseId, id), { method: "DELETE" });
export const restoreAssessment = (courseId: string, id: string) =>
  lmsFetch<AssessmentStaffOut>(`${one(courseId, id)}/restore`, { method: "POST" });

// ---- Sections ----
export const addSection = (courseId: string, id: string, body: SectionIn) =>
  lmsFetch<SectionOut>(`${one(courseId, id)}/sections`, { method: "POST", body });
export const updateSection = (courseId: string, id: string, sectionId: string, body: SectionIn) =>
  lmsFetch<SectionOut>(`${one(courseId, id)}/sections/${e(sectionId)}`, { method: "PATCH", body });
export const deleteSection = (courseId: string, id: string, sectionId: string) =>
  lmsFetch<void>(`${one(courseId, id)}/sections/${e(sectionId)}`, { method: "DELETE" });
export const reorderSections = (courseId: string, id: string, sectionIds: string[]) =>
  lmsFetch<AssessmentStaffOut>(`${one(courseId, id)}/sections/order`, { method: "PUT", body: { section_ids: sectionIds } });

// ---- Items ----
export const addItem = (courseId: string, id: string, sectionId: string, body: ItemCreateIn) =>
  lmsFetch<ItemOut[]>(`${one(courseId, id)}/sections/${e(sectionId)}/items`, { method: "POST", body });
export const addItemsBulk = (courseId: string, id: string, sectionId: string, body: BulkAddIn) =>
  lmsFetch<BulkAddOut>(`${one(courseId, id)}/sections/${e(sectionId)}/items/bulk`, { method: "POST", body });
export const updateItem = (courseId: string, id: string, itemId: string, body: ItemUpdateIn) =>
  lmsFetch<ItemOut>(`${one(courseId, id)}/items/${e(itemId)}`, { method: "PATCH", body });
export const deleteItem = (courseId: string, id: string, itemId: string) =>
  lmsFetch<void>(`${one(courseId, id)}/items/${e(itemId)}`, { method: "DELETE" });
export const reorderItems = (courseId: string, id: string, sectionId: string, body: ItemsOrderIn) =>
  lmsFetch<SectionOut>(`${one(courseId, id)}/sections/${e(sectionId)}/items/order`, { method: "PUT", body });

// ---- Publish ----
export const validateAssessment = (courseId: string, id: string) =>
  lmsFetch<ValidationOut>(`${one(courseId, id)}/validate`, { method: "POST" });
export const publishAssessment = (courseId: string, id: string, confirm = false) =>
  lmsFetch<PublishOut>(`${one(courseId, id)}/publish`, { method: "POST", body: { confirm } });
export const unpublishAssessment = (courseId: string, id: string) =>
  lmsFetch<AssessmentStaffOut>(`${one(courseId, id)}/unpublish`, { method: "POST" });
export const listAssessmentVersions = (courseId: string, id: string, opts: { cursor?: string | null; limit?: number } = {}) =>
  lmsFetch<PageOut<VersionOut>>(`${one(courseId, id)}/versions`, { params: opts });

/** Staff "preview as student": starts a preview attempt; navigate to the player with the returned attempt id. */
export const startPreview = (courseId: string, id: string, language?: Lang) =>
  lmsFetch<PreviewStartOut>(`${one(courseId, id)}/preview`, { method: "POST", body: language ? { language } : {} });

/** Student start/resume (200 resume, 201 new). Returns at least the attempt id; full shape is `AttemptStateOut` (attemptTypes.ts). */
export const startAssessmentAttempt = (courseId: string, id: string, language?: Lang) =>
  lmsFetch<PreviewStartOut>(`${one(courseId, id)}/attempts`, { method: "POST", body: language ? { language } : {} });
