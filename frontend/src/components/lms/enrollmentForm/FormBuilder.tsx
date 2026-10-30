"use client";

// Phase 9 S4: the enrollment form as one page per object (`/courses/{id}/settings/enrollment-form`, PHASE_9_DESIGN
// 2.4, 4.6, 6, 8.1, 8.4) with Edit · Preview tabs (`?tab=`). Versions: one draft and one active form per course; a form
// that has answers is immutable (the teacher makes a new version). Fields use the 8c row pattern: one "⋯" menu per
// row with edit, move up / down and remove. Field keys are generated from the label, never typed.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, ChevronDown, ChevronUp, Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  FIELDS_PER_FORM_MAX, activateForm, createFormDraft, deleteFormDraft, getForm, keyFromLabel, listFormVersions,
  newFormVersion, updateForm, type EnrollmentFormSummaryOut,
} from "@/lib/lms/enrollmentForms";
import { cleanLocalized, pickLocalized } from "@/lib/lms/localized";
import { templateUi } from "@/lib/lms/templates";
import type { CourseStaffOut, EnrollmentFormOut, FieldIn, FieldOut, LocalizedText } from "@/lib/lms/types";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import {
  Badge, Button, ConfirmDialog, EmptyState, ErrorState, LoadingState, MenuButton, PageHeader, TabPanel, Tabs, toast,
} from "@/components/ui";
import { useApplicationErrorText } from "@/components/lms/catalog/useApplicationErrorText";
import { FieldEditor, defaultPii } from "./FieldEditor";
import { FormPreview } from "./FormPreview";
import type { RenderableForm } from "./FormRenderer";

const TABS_ID = "enrollment-form";
type TabId = "edit" | "preview";
type Row = FieldIn & { uid: string };

let uidSeq = 0;
const nextUid = () => `f${(uidSeq += 1)}`;

function toRows(form: EnrollmentFormOut | null): Row[] {
  return (form?.fields ?? []).map((f) => ({
    uid: nextUid(), key: f.key, type: f.type, label: f.label, help: f.help, options: f.options, bounds: f.bounds,
    required: f.required, pii_category: f.pii_category, max_len: f.max_len,
  }));
}

/** Rows as the renderer's `FieldOut` (Preview shows unsaved edits too). */
function rowsAsFields(rows: Row[]): FieldOut[] {
  return rows.map((r, i) => ({
    id: r.uid, key: r.key || r.uid, type: r.type, label: r.label, help: r.help ?? null, options: r.options ?? null,
    bounds: r.bounds ?? null, required: !!r.required, position: i, pii_category: r.pii_category, max_len: r.max_len ?? null,
  }));
}

function statusTone(s: EnrollmentFormSummaryOut["status"]) {
  return s === "active" ? "success" : s === "draft" ? "info" : "neutral";
}

export function FormBuilder({ course }: { course: CourseStaffOut }) {
  const { lang, t } = useTranslation();
  const errorText = useApplicationErrorText();
  const router = useRouter();
  const pathname = usePathname() ?? "";
  const search = useSearchParams();
  const param = search?.get("tab");
  const tab: TabId = param === "preview" ? "preview" : "edit";
  const isTeacher = course.my_enrollment.role === "teacher";
  const locked = templateUi(course).locked;
  const { languages, default_language: defaultLanguage } = course;

  const [versions, setVersions] = useState<EnrollmentFormSummaryOut[]>([]);
  const [form, setForm] = useState<EnrollmentFormOut | null>(null);
  const [title, setTitle] = useState<LocalizedText>({});
  const [intro, setIntro] = useState<LocalizedText>({});
  const [rows, setRows] = useState<Row[]>([]);
  const [openUid, setOpenUid] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [busy, setBusy] = useState<null | "save" | "activate" | "create" | "delete" | "version" | "view">(null);
  const [error, setError] = useState<unknown>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<null | "delete" | "activate" | "remove">(null);
  const [removeUid, setRemoveUid] = useState<string | null>(null);

  const show = useCallback((f: EnrollmentFormOut | null) => {
    setForm(f);
    setTitle(f?.title ?? {});
    setIntro(f?.intro ?? {});
    setRows(toRows(f));
    setOpenUid(null);
    setDirty(false);
    setLocalError(null);
  }, []);

  const load = useCallback(async (preferId?: string) => {
    setLoading(true);
    setLoadError(null);
    try {
      const vs = await listFormVersions(course.id);
      setVersions(vs);
      const pick = (preferId && vs.find((v) => v.id === preferId)) || vs.find((v) => v.status === "draft")
        || vs.find((v) => v.status === "active") || vs[0];
      show(pick ? await getForm(course.id, pick.id) : null);
    } catch (e) {
      setLoadError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id, show]);
  useEffect(() => { void load(); }, [load]);

  const switchTab = (id: string) => {
    const p = new URLSearchParams(search?.toString() ?? "");
    p.set("tab", id);
    router.replace(`${pathname}?${p}`, { scroll: false });
  };

  const editable = !!form && isTeacher && !locked && form.status !== "retired" && !form.answered;
  const hasDraft = versions.some((v) => v.status === "draft");
  const active = versions.find((v) => v.status === "active") ?? null;
  const touch = () => { setDirty(true); setLocalError(null); };

  const setRow = (uid: string, f: FieldIn) => { setRows((rs) => rs.map((r) => (r.uid === uid ? { ...f, uid } : r))); touch(); };
  const move = (i: number, d: -1 | 1) => {
    setRows((rs) => {
      const j = i + d;
      if (j < 0 || j >= rs.length) return rs;
      const n = rs.slice();
      [n[i], n[j]] = [n[j], n[i]];
      return n;
    });
    touch();
  };
  const addField = () => {
    const uid = nextUid();
    setRows((rs) => [...rs, { uid, key: "", type: "short_text", label: {}, help: null, options: null, bounds: null,
      required: true, pii_category: defaultPii("short_text"), max_len: null }]);
    setOpenUid(uid);
    touch();
  };

  /** Client checks the server repeats (labels in the default language, choice options); returns an i18n key. */
  const check = (): string | null => {
    for (const r of rows) {
      if (!(r.label[defaultLanguage] ?? "").trim()) return "enrollmentForm.errors.labelRequired";
      if ((r.type === "single_choice" || r.type === "multi_choice")
        && (!(r.options ?? []).length || (r.options ?? []).some((o) => !(o.label[defaultLanguage] ?? "").trim()))) {
        return "enrollmentForm.errors.optionRequired";
      }
    }
    return null;
  };

  const orNull = (v: LocalizedText): LocalizedText | null => {
    const c = cleanLocalized(v, languages);
    return Object.keys(c).length ? c : null;
  };

  const payload = () => {
    const taken = new Set(rows.filter((r) => r.key).map((r) => r.key));
    const fields: FieldIn[] = rows.map((r) => {
      let key = r.key;
      if (!key) {
        key = keyFromLabel(pickLocalized(r.label, defaultLanguage, defaultLanguage) || "field", taken);
        taken.add(key);
      }
      return {
        type: r.type, bounds: r.bounds ?? null, required: !!r.required, pii_category: r.pii_category, max_len: r.max_len ?? null,
        key, label: cleanLocalized(r.label, languages), help: r.help ? orNull(r.help) : null,
        options: r.options ? r.options.map((o) => ({ ...o, label: cleanLocalized(o.label, languages) })) : null,
      };
    });
    return { title: orNull(title), intro: orNull(intro), fields };
  };

  const run = async (kind: NonNullable<typeof busy>, fn: () => Promise<void>) => {
    setBusy(kind);
    setError(null);
    try {
      await fn();
      return true;
    } catch (e) {
      setError(e);
      return false;
    } finally {
      setBusy(null);
    }
  };

  const save = async (): Promise<EnrollmentFormOut | null> => {
    if (!form) return null;
    const bad = check();
    if (bad) { setLocalError(bad); return null; }
    let out: EnrollmentFormOut | null = null;
    const ok = await run("save", async () => {
      out = await updateForm(course.id, form.id, payload());
      show(out);
      setVersions(await listFormVersions(course.id));
    });
    if (ok) toast.success(t("enrollmentForm.saved"));
    return ok ? out : null;
  };

  const activate = async () => {
    if (!form) return;
    if (dirty && !(await save())) { setConfirm(null); return; }
    const ok = await run("activate", async () => {
      await activateForm(course.id, form.id);
      await load(form.id);
    });
    setConfirm(null);
    if (ok) toast.success(t("enrollmentForm.activated"));
  };

  const create = () => run("create", async () => {
    const f = await createFormDraft(course.id, { title: null, intro: null, fields: [] });
    await load(f.id);
  });

  const newVersion = () => form && run("version", async () => {
    const f = await newFormVersion(course.id, form.id);
    await load(f.id);
    toast.success(t("enrollmentForm.versionCreated"));
  });

  const removeDraft = async () => {
    if (!form) return;
    const ok = await run("delete", async () => {
      await deleteFormDraft(course.id, form.id);
      await load();
    });
    if (ok) setConfirm(null);
  };

  const view = (id: string) => run("view", async () => show(await getForm(course.id, id)));

  const previewForm: RenderableForm = useMemo(
    () => ({ title, intro, fields: rowsAsFields(rows) }), [title, intro, rows],
  );

  const base = `/${lang}/courses/${course.id}`;
  const header = (
    <PageHeader title={t("enrollmentForm.title")} className="mb-4"
      breadcrumbs={[{ label: t("courses.settings.tab"), href: `${base}/settings` }, { label: t("enrollmentForm.title") }]}
      badge={form ? <Badge tone={statusTone(form.status)}>{t(`enrollmentForm.status.${form.status}`)}</Badge> : undefined}
      description={form ? t("enrollmentForm.versionN", { n: form.version }) : undefined} />
  );

  if (loading && !form && !loadError) return <div className="max-w-4xl">{header}<LoadingState rows={4} /></div>;
  if (loadError) {
    return <div className="max-w-4xl">{header}<ErrorState message={errorText(loadError)} onRetry={() => void load()} retrying={loading} /></div>;
  }
  if (locked) {
    return (
      <div className="max-w-4xl">{header}
        <p className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">{t("enrollmentForm.ortLocked")}</p>
      </div>
    );
  }

  if (!form) {
    return (
      <div className="max-w-4xl">{header}
        <EmptyState title={t("enrollmentForm.empty.title")} description={t("enrollmentForm.empty.body")}
          action={isTeacher ? <Button loading={busy === "create"} leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />} onClick={() => void create()}>{t("enrollmentForm.empty.create")}</Button> : undefined} />
        {error ? <ErrorState variant="inline" message={errorText(error)} className="mt-3" /> : null}
      </div>
    );
  }

  const fieldTitle = (r: Row, i: number) => pickLocalized(r.label, lang, defaultLanguage) || t("enrollmentForm.field.untitled", { n: i + 1 });

  return (
    <div className="max-w-4xl">
      {header}
      <Tabs id={TABS_ID} label={t("enrollmentForm.tabs.label")} value={tab} onChange={switchTab} items={[
        { id: "edit", label: t("enrollmentForm.tabs.edit") },
        { id: "preview", label: t("enrollmentForm.tabs.preview") },
      ]} />

      <TabPanel tabsId={TABS_ID} value="edit" hidden={tab !== "edit"}>
        <div className="space-y-6">
          {/* PII notice: forms must not ask for special categories (design 6). */}
          <div className="flex items-start gap-3 rounded-2xl border border-warning-200 bg-warning-50 p-4 text-sm leading-6 text-warning-900">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
            <p>{t("enrollmentForm.piiNotice")}</p>
          </div>

          {form.answered && (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-700">
              <p>{t("enrollmentForm.immutable")}</p>
              {isTeacher && !hasDraft && (
                <Button variant="secondary" size="sm" className="mt-3" loading={busy === "version"} onClick={() => void newVersion()}>
                  {t("enrollmentForm.newVersion")}
                </Button>
              )}
            </div>
          )}
          {form.status === "retired" && !form.answered && (
            <p className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-700">{t("enrollmentForm.retiredNote")}</p>
          )}
          {form.status === "draft" && active && (
            <p className="rounded-2xl border border-brand-200 bg-brand-50 p-4 text-sm leading-6 text-brand-900">
              {t("enrollmentForm.draftReplaces", { n: active.version })}
            </p>
          )}
          {!isTeacher && <p className="text-sm leading-6 text-slate-600">{t("enrollmentForm.readOnly")}</p>}

          <section className="space-y-5 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
            <LocalizedTextInput label={t("enrollmentForm.formTitle")} languages={languages} defaultLanguage={defaultLanguage}
              value={title} onChange={(v) => { setTitle(v); touch(); }} maxLength={200} disabled={!editable} />
            <LocalizedTextInput label={t("enrollmentForm.intro")} languages={languages} defaultLanguage={defaultLanguage}
              value={intro} onChange={(v) => { setIntro(v); touch(); }} multiline maxLength={2000} disabled={!editable} />
          </section>

          <section aria-labelledby="ef-fields" className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="ef-fields" className="text-lg font-semibold leading-7 text-slate-900">{t("enrollmentForm.fields")}</h2>
              <span className="text-sm text-slate-600">{t("enrollmentForm.fieldCount", { count: rows.length, max: FIELDS_PER_FORM_MAX })}</span>
            </div>
            {rows.length === 0 && <p className="rounded-2xl border border-dashed border-slate-300 p-4 text-sm leading-6 text-slate-600">{t("enrollmentForm.noFields")}</p>}
            <ol className="space-y-3">
              {rows.map((r, i) => {
                const isOpen = openUid === r.uid;
                const name = fieldTitle(r, i);
                return (
                  <li key={r.uid} className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                    <div className="flex items-start gap-2 p-3 sm:p-4">
                      <button type="button" aria-expanded={isOpen} aria-controls={`ef-row-${r.uid}`}
                        onClick={() => setOpenUid(isOpen ? null : r.uid)}
                        className="flex min-h-11 min-w-0 flex-1 items-start gap-3 rounded-lg text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600">
                        <span className="mt-0.5 text-sm font-semibold text-slate-500">{i + 1}.</span>
                        <span className="min-w-0 flex-1">
                          <span className="block break-words text-base font-medium leading-6 text-slate-900 sm:text-sm">{name}</span>
                          <span className="mt-1 flex flex-wrap gap-1.5">
                            <Badge>{t(`enrollmentForm.types.${r.type}`)}</Badge>
                            {r.required && <Badge tone="info">{t("enrollmentForm.field.requiredBadge")}</Badge>}
                            {r.pii_category !== "none" && <Badge tone="warning">{t(`enrollmentForm.pii.${r.pii_category}`)}</Badge>}
                          </span>
                        </span>
                        {isOpen ? <ChevronUp className="mt-1 h-5 w-5 shrink-0 text-slate-500" aria-hidden="true" /> : <ChevronDown className="mt-1 h-5 w-5 shrink-0 text-slate-500" aria-hidden="true" />}
                      </button>
                      {editable && (
                        <MenuButton variant="secondary" size="sm"
                          label={<>⋯<span className="sr-only">{t("enrollmentForm.field.actions", { name })}</span></>}
                          items={[
                            { id: "edit", label: t("enrollmentForm.field.edit") },
                            { id: "up", label: t("enrollmentForm.field.moveUp"), disabled: i === 0 },
                            { id: "down", label: t("enrollmentForm.field.moveDown"), disabled: i === rows.length - 1 },
                            { id: "remove", label: t("enrollmentForm.field.remove") },
                          ]}
                          onSelect={(id) => {
                            if (id === "edit") setOpenUid(r.uid);
                            else if (id === "up") move(i, -1);
                            else if (id === "down") move(i, 1);
                            else { setRemoveUid(r.uid); setConfirm("remove"); }
                          }} />
                      )}
                    </div>
                    {isOpen && (
                      <div id={`ef-row-${r.uid}`} className="border-t border-slate-100 p-3 sm:p-4">
                        <FieldEditor field={r} onChange={(f) => setRow(r.uid, f)} languages={languages} defaultLanguage={defaultLanguage}
                          disabled={!editable} idPrefix={`ef-${r.uid}`} />
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
            {editable && (
              <Button variant="secondary" leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}
                disabled={rows.length >= FIELDS_PER_FORM_MAX} onClick={addField}>
                {t("enrollmentForm.addField")}
              </Button>
            )}
          </section>

          {localError || error ? (
            <ErrorState variant="inline" message={localError ? t(localError) : errorText(error)} />
          ) : null}

          {editable && (
            <div className="sticky bottom-0 z-10 -mx-4 flex flex-wrap items-center gap-2 border-t border-slate-200 bg-white/95 px-4 py-2 backdrop-blur sm:mx-0 sm:rounded-2xl sm:border sm:py-3">
              <Button loading={busy === "save"} disabled={!dirty || !!busy} onClick={() => void save()}>{t("lms.common.save")}</Button>
              {form.status === "draft" && (
                <Button variant="secondary" disabled={!!busy || rows.length === 0} loading={busy === "activate"}
                  onClick={() => { setError(null); setConfirm("activate"); }}>
                  {dirty ? t("enrollmentForm.saveAndActivate") : t("enrollmentForm.activate")}
                </Button>
              )}
              {dirty && <Button variant="link" disabled={!!busy} onClick={() => show(form)}>{t("enrollmentForm.discard")}</Button>}
              {form.status === "draft" && (
                <Button variant="dangerOutline" className="sm:ml-auto" disabled={!!busy} onClick={() => { setError(null); setConfirm("delete"); }}>
                  {t("enrollmentForm.deleteDraft")}
                </Button>
              )}
              {dirty && <span role="status" className="text-sm text-slate-600">{t("enrollmentForm.unsaved")}</span>}
            </div>
          )}

          {isTeacher && !editable && !form.answered && form.status === "retired" && !hasDraft && (
            <Button variant="secondary" loading={busy === "version"} onClick={() => void newVersion()}>{t("enrollmentForm.newVersion")}</Button>
          )}

          {/* Versions (newest first); viewing another one discards nothing: switching is blocked while there are unsaved edits. */}
          {versions.length > 1 && (
            <section aria-labelledby="ef-versions" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
              <h2 id="ef-versions" className="text-lg font-semibold leading-7 text-slate-900">{t("enrollmentForm.versions.title")}</h2>
              {dirty && <p className="mt-1 text-sm text-slate-600">{t("enrollmentForm.versions.saveFirst")}</p>}
              <ul className="mt-3 divide-y divide-slate-100">
                {versions.map((v) => (
                  <li key={v.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                    <span className="text-sm font-medium text-slate-900">{t("enrollmentForm.versionN", { n: v.version })}</span>
                    <Badge tone={statusTone(v.status)}>{t(`enrollmentForm.status.${v.status}`)}</Badge>
                    {v.answered && <Badge>{t("enrollmentForm.versions.answered")}</Badge>}
                    <span className="text-sm text-slate-600">{t("enrollmentForm.versions.fields", { count: v.field_count })}</span>
                    {v.id === form.id
                      ? <span className="ml-auto text-sm text-slate-600">{t("enrollmentForm.versions.shown")}</span>
                      : <Button variant="link" className="ml-auto" disabled={dirty || !!busy} onClick={() => void view(v.id)}>{t("enrollmentForm.versions.view")}</Button>}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </TabPanel>

      {tab === "preview" && (
        <TabPanel tabsId={TABS_ID} value="preview">
          <FormPreview form={previewForm} defaultLanguage={defaultLanguage} languages={languages} />
        </TabPanel>
      )}

      <ConfirmDialog open={confirm === "activate"} busy={busy === "activate" || busy === "save"} title={t("enrollmentForm.activateTitle")}
        object={t("enrollmentForm.versionN", { n: form.version })}
        effect={active ? t("enrollmentForm.activateBodyReplace", { n: active.version }) : t("enrollmentForm.activateBody")}
        error={error && confirm === "activate" ? <ErrorState variant="inline" message={errorText(error)} /> : undefined}
        confirmLabel={t("enrollmentForm.activate")} onConfirm={() => void activate()} onCancel={() => setConfirm(null)} />
      <ConfirmDialog open={confirm === "delete"} tone="danger" busy={busy === "delete"} title={t("enrollmentForm.deleteTitle")}
        object={t("enrollmentForm.versionN", { n: form.version })} effect={t("enrollmentForm.deleteBody")}
        error={error && confirm === "delete" ? <ErrorState variant="inline" message={errorText(error)} /> : undefined}
        confirmLabel={t("enrollmentForm.deleteDraft")} onConfirm={() => void removeDraft()} onCancel={() => setConfirm(null)} />
      <ConfirmDialog open={confirm === "remove"} tone="danger" title={t("enrollmentForm.field.removeTitle")}
        object={(() => { const i = rows.findIndex((r) => r.uid === removeUid); return i >= 0 ? fieldTitle(rows[i], i) : undefined; })()}
        effect={t("enrollmentForm.field.removeBody")} confirmLabel={t("enrollmentForm.field.remove")}
        onConfirm={() => { setRows((rs) => rs.filter((r) => r.uid !== removeUid)); setRemoveUid(null); setConfirm(null); touch(); }}
        onCancel={() => { setRemoveUid(null); setConfirm(null); }} />
    </div>
  );
}
