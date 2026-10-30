"use client";

// Phase 8a S4a (PHASE_8A_DESIGN 8.1 `AddItemMenu`): add an item to a module. Page, file and assignment pick an existing
// target (with a way to create one); "New quiz" creates the 7a quiz assignment and its item in one call, then opens
// the 7c quiz editor; a link takes a web address; a header is a title only. Optional: the title shown in the module,
// visibility and a completion requirement (types allowed by the kind).
// Phase 8c S2 (PHASE_8C_DESIGN §3.3, §3.4): opened from the grouped "+ Add" menu with `initialKind` (the kind radios
// are then hidden). "New page" leads to `/pages/new?module=&from=`; "Upload" and "New assignment" open their dialogs
// over this one and add the new target to the module; the quiz editor and the assignment page get `from` (back to
// the module). `PlaceInModuleDialog` puts an unsorted target into a module at a chosen position.
import React, { useCallback, useEffect, useId, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Upload } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { cleanLocalized, pickLocalized } from "@/lib/lms/localized";
import { listAssignments } from "@/lib/lms/assignments";
import type { AssignmentStaffOut, AssignmentStaffSummaryOut } from "@/lib/lms/assignmentTypes";
import { addItem, createQuizItem, listCourseFilesForPicker, listPagesForPicker } from "@/lib/lms/modules";
import type { ItemIn, ItemKind, ItemStaffOut, ModuleStaffOut, RequirementType } from "@/lib/lms/modulesTypes";
import { withFrom } from "@/lib/lms/nav";
import type { CourseFileStaffOut } from "@/lib/lms/pagesTypes";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { Badge, Button, Checkbox, Dialog, FieldLabel, Input, LinkButton, Pagination, Select, Skeleton, Switch } from "@/components/ui";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { AssignmentEditorDialog } from "@/components/lms/assignments/AssignmentEditorDialog";
import { UploadFileDialog } from "@/components/lms/courseFiles/UploadFileDialog";
import { ItemKindIcon, useItemKindText, useModuleErrorText } from "./moduleUi";
import { RequirementFields, requirementBody, type CourseLangs } from "./OutlineDialogs";

export type AddKind = ItemKind | "quiz";
const ADD_KINDS: AddKind[] = ["page", "file", "assignment", "quiz", "url", "header"];

/** The Course page fragment of a module: the `from` of every object opened from the outline (§5.3). */
export const moduleAnchor = (base: string, moduleId: string) => `${base}#m-${moduleId}`;

interface Pick { id: string; title: string; meta?: string; draft: boolean; icon: React.ReactNode }

/** A paged radio list of existing targets (pages, files or assignments). */
function PickList({ load, picked, onPick, emptyText, create, label, disabled }: {
  load: (cursor: string | null) => Promise<{ items: Pick[]; next: string | null }>;
  picked: string | null;
  onPick: (id: string) => void;
  emptyText: string;
  /** The way to create a new target (a link or a button). */
  create?: React.ReactNode;
  label: string;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const errorText = useModuleErrorText();
  const name = useId();
  const [items, setItems] = useState<Pick[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const fetchPage = useCallback(async (c: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await load(c);
      setItems((prev) => (c && prev ? [...prev, ...page.items] : page.items));
      setCursor(page.next);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [load]);
  useEffect(() => { void fetchPage(null); }, [fetchPage]);

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium leading-6 text-slate-800">{label}</legend>
      {error ? (
        <div className="flex flex-wrap items-center gap-3 text-sm text-danger-800">
          <span role="alert">{errorText(error)}</span>
          <Button size="sm" variant="secondary" onClick={() => void fetchPage(cursor)}>{t("lms.common.retry")}</Button>
        </div>
      ) : null}
      {!items && !error ? (
        <div aria-hidden="true" className="space-y-2"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
      ) : items && items.length === 0 ? (
        <p className="rounded-xl bg-slate-50 px-3 py-3 text-sm text-slate-700">{emptyText}</p>
      ) : (
        <div className="max-h-72 overflow-y-auto rounded-xl border border-slate-200">
          <ul className="divide-y divide-slate-100">
            {(items ?? []).map((p) => (
              <li key={p.id}>
                <label className="flex min-h-11 cursor-pointer items-start gap-3 px-3 py-2.5 hover:bg-slate-50">
                  <input type="radio" name={name} className="mt-1 h-4 w-4 shrink-0 accent-brand-600" checked={picked === p.id}
                    disabled={disabled} onChange={() => onPick(p.id)} />
                  <span className="mt-0.5 text-slate-500">{p.icon}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block break-words text-base leading-6 text-slate-900 sm:text-sm">{p.title}</span>
                    {(p.meta || p.draft) && (
                      <span className="mt-0.5 flex flex-wrap items-center gap-2 text-sm text-slate-600">
                        {p.meta && <span>{p.meta}</span>}
                        {p.draft && <Badge>{t("modules.editor.draft")}</Badge>}
                      </span>
                    )}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <Pagination nextCursor={cursor} loading={loading} onLoadMore={() => void fetchPage(cursor)} className="pb-2" />
        </div>
      )}
      {create}
    </fieldset>
  );
}

export function AddItemDialog({ open, module, courseId, base, langs, initialKind, allowNewAssignment = true, onAdded, onClose }: {
  open: boolean;
  module: ModuleStaffOut;
  courseId: string;
  base: string;
  langs: CourseLangs;
  /** Phase 8c S2: the kind chosen in the "+ Add" menu; the kind radios are then hidden. */
  initialKind?: AddKind;
  /** Phase 8c S2: false in ORT courses (non-quiz assignments stay out of them, 7a). */
  allowNewAssignment?: boolean;
  onAdded: () => void;
  onClose: () => void;
}) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const kindText = useItemKindText();
  const errorText = useModuleErrorText();
  const formId = useId();
  const kindName = useId();
  const [kind, setKind] = useState<AddKind>(initialKind ?? "page");
  const [target, setTarget] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState<LocalizedText>({});
  const [visible, setVisible] = useState(true);
  const [req, setReq] = useState<{ type: RequirementType | null; threshold: string }>({ type: null, threshold: "" });
  const [quizLangs, setQuizLangs] = useState<Lang[]>([langs.defaultLanguage]);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // Phase 8c S2: "Upload" and "New assignment" open their own dialog over this one
  const [sub, setSub] = useState<null | "upload" | "assignment">(null);
  const from = moduleAnchor(base, module.id);
  const moduleName = pickLocalized(module.title, lang, langs.defaultLanguage) || t("modules.untitledModule");

  const chooseKind = (k: AddKind) => {
    setKind(k);
    setTarget(null);
    setReq({ type: null, threshold: "" });
    setTouched(false);
    setError(null);
  };

  const loadPages = useCallback(async (c: string | null) => {
    const page = await listPagesForPicker(courseId, c);
    return {
      items: page.items.filter((p) => !p.deleted_at).map((p) => ({
        id: p.id, title: p.title || t("modules.untitledItem"), meta: t(`courses.languages.${p.language}`), draft: !p.published,
        icon: <ItemKindIcon kind="page" />,
      })),
      next: page.next_cursor,
    };
  }, [courseId, t]);
  const loadFiles = useCallback(async (c: string | null) => {
    const page = await listCourseFilesForPicker(courseId, c);
    return {
      items: page.items.filter((f) => !f.deleted_at).map((f) => ({
        id: f.id, title: f.title || t("modules.untitledItem"), meta: f.folder || undefined, draft: !f.published, icon: <ItemKindIcon kind="file" />,
      })),
      next: page.next_cursor,
    };
  }, [courseId, t]);
  const loadAssignments = useCallback(async (c: string | null) => {
    const page = await listAssignments(courseId, { cursor: c, limit: 50 });
    return {
      items: (page.items as AssignmentStaffSummaryOut[]).filter((a) => !a.deleted_at).map((a) => ({
        id: a.id, title: pickLocalized(a.title, lang, langs.defaultLanguage) || t("assignments.untitled"), meta: t(`assignments.kinds.${a.kind}`),
        draft: !a.published, icon: <ItemKindIcon kind="assignment" assignmentKind={a.kind} />,
      })),
      next: page.next_cursor,
    };
  }, [courseId, lang, langs.defaultLanguage, t]);

  const cleaned = cleanLocalized(title, langs.languages);
  const hasTitle = Object.keys(cleaned).length > 0;
  const urlOk = /^https?:\/\/\S+$/i.test(url.trim());
  const reqBody = requirementBody(req);
  const valid =
    kind === "quiz" ? hasTitle && quizLangs.length > 0
      : kind === "header" ? hasTitle
        : kind === "url" ? urlOk && reqBody !== undefined
          : !!target && reqBody !== undefined;

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setTouched(true);
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      if (kind === "quiz") {
        const out = await createQuizItem(courseId, module.id, { kind: "quiz", title: cleaned, quiz: { preset: "none", languages: quizLangs } });
        router.push(withFrom(`${base}/assessments/${out.assessment_id}/edit`, from));
        return;
      }
      const body: ItemIn = { kind, published: visible };
      if (kind === "page") body.page_id = target!;
      if (kind === "file") body.file_id = target!;
      if (kind === "assignment") body.assignment_id = target!;
      if (kind === "url") body.url = url.trim();
      if (hasTitle) body.title_override = cleaned;
      if (kind !== "header" && reqBody) body.requirement = reqBody;
      await addItem(courseId, module.id, body);
      onAdded();
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  /** Phase 8c S2: a target created in a nested dialog goes straight into the module (visible, no requirement). */
  const addCreated = async (body: ItemIn, next?: string) => {
    setSub(null);
    setBusy(true);
    setError(null);
    try {
      await addItem(courseId, module.id, body);
      if (next) { router.push(next); return; }
      onAdded();
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };
  const onFileUploaded = (f?: CourseFileStaffOut) => {
    if (!f) { setSub(null); return; }
    void addCreated({ kind: "file", file_id: f.id, published: true });
  };
  const onAssignmentCreated = (a: AssignmentStaffOut) => {
    const next = a.kind === "quiz" && a.assessment_id
      ? withFrom(`${base}/assessments/${a.assessment_id}/edit`, from)
      : withFrom(`${base}/assignments/${a.id}?tab=settings`, from);
    void addCreated({ kind: "assignment", assignment_id: a.id, published: true }, next);
  };

  const toggleLang = (l: Lang) => setQuizLangs((p) => (p.includes(l) ? p.filter((x) => x !== l) : [...p, l]));
  const itemKind: ItemKind = kind === "quiz" ? "assignment" : kind;
  const plus = <Plus aria-hidden="true" className="h-4 w-4" />;

  return (
    <Dialog open={open} onClose={onClose} busy={busy} size="lg" title={t("modules.add.title")}
      description={initialKind
        ? t("coursePage.addDescription", { kind: initialKind === "quiz" ? t("coursePage.addItems.quiz") : kindText(initialKind), module: moduleName })
        : moduleName}
      footer={(
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t("lms.common.cancel")}</Button>
          <Button type="submit" form={formId} loading={busy}>{kind === "quiz" ? t("modules.add.createQuiz") : t("modules.add.submit")}</Button>
        </>
      )}>
      <form id={formId} onSubmit={(e) => void submit(e)} noValidate className="space-y-5">
        {!initialKind && (
          <fieldset>
            <legend className="mb-1 text-sm font-medium leading-6 text-slate-800">{t("modules.add.kindLabel")}</legend>
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              {ADD_KINDS.map((k) => (
                <label key={k} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-slate-200 px-3 py-2 has-[:checked]:border-brand-600 has-[:checked]:bg-brand-50">
                  <input type="radio" name={kindName} className="h-4 w-4 shrink-0 accent-brand-600" checked={kind === k} disabled={busy} onChange={() => chooseKind(k)} />
                  <ItemKindIcon kind={k === "quiz" ? "assignment" : k} assignmentKind={k === "quiz" ? "quiz" : undefined} className="h-5 w-5 text-slate-600" />
                  <span className="text-base leading-6 text-slate-900 sm:text-sm">{k === "quiz" ? t("modules.add.newQuiz") : kindText(k)}</span>
                </label>
              ))}
            </div>
          </fieldset>
        )}

        {kind === "page" && (
          <PickList key="page" load={loadPages} picked={target} onPick={setTarget} label={t("modules.add.pickPage")} disabled={busy}
            emptyText={t("modules.add.noPages")}
            create={(
              <LinkButton variant="link" href={withFrom(`${base}/pages/new?module=${encodeURIComponent(module.id)}`, from)} leftIcon={plus}>
                {t("modules.add.createPage")}
              </LinkButton>
            )} />
        )}
        {kind === "file" && (
          <PickList key="file" load={loadFiles} picked={target} onPick={setTarget} label={t("modules.add.pickFile")} disabled={busy}
            emptyText={t("modules.add.noFiles")}
            create={(
              <Button variant="link" disabled={busy} onClick={() => setSub("upload")} leftIcon={<Upload aria-hidden="true" className="h-4 w-4" />}>
                {t("modules.add.uploadFile")}
              </Button>
            )} />
        )}
        {kind === "assignment" && (
          <PickList key="assignment" load={loadAssignments} picked={target} onPick={setTarget} label={t("modules.add.pickAssignment")} disabled={busy}
            emptyText={t("modules.add.noAssignments")}
            create={allowNewAssignment ? (
              <Button variant="link" disabled={busy} onClick={() => setSub("assignment")} leftIcon={plus}>{t("modules.add.createAssignment")}</Button>
            ) : undefined} />
        )}
        {touched && !target && (kind === "page" || kind === "file" || kind === "assignment") && (
          <p role="alert" className="text-sm text-danger-700">{t("modules.add.pickRequired")}</p>
        )}

        {kind === "url" && (
          <Input type="url" inputMode="url" label={t("modules.add.url")} hint={t("modules.add.urlHint")} value={url} disabled={busy}
            placeholder="https://" onChange={(e) => setUrl(e.target.value)} error={touched && !urlOk ? t("modules.errors.url_invalid") : undefined} />
        )}

        {kind === "quiz" ? (
          <>
            <LocalizedTextInput label={t("modules.add.quizTitle")} languages={langs.languages} defaultLanguage={langs.defaultLanguage}
              value={title} onChange={setTitle} maxLength={200} required disabled={busy} />
            {touched && !hasTitle && <p role="alert" className="text-sm text-danger-700">{t("modules.settings.titleRequired")}</p>}
            {langs.languages.length > 1 && (
              <div>
                <FieldLabel>{t("assessments.create.languages")}</FieldLabel>
                <div className="flex flex-wrap gap-x-5">
                  {langs.languages.map((l) => (
                    <Checkbox key={l} label={t(`courses.languages.${l}`)} checked={quizLangs.includes(l)} disabled={busy} onChange={() => toggleLang(l)} />
                  ))}
                </div>
              </div>
            )}
            <p className="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700">{t("modules.add.quizNext")}</p>
          </>
        ) : (
          <>
            <LocalizedTextInput label={kind === "header" ? t("modules.add.headerTitle") : t("modules.add.titleOverride")}
              languages={langs.languages} defaultLanguage={langs.defaultLanguage} value={title} onChange={setTitle} maxLength={200}
              required={kind === "header"} disabled={busy} />
            {kind !== "header" && <p className="-mt-3 text-sm text-slate-600">{t("modules.add.titleOverrideHint")}</p>}
            {touched && kind === "header" && !hasTitle && <p role="alert" className="text-sm text-danger-700">{t("modules.add.headerRequired")}</p>}
            <Switch label={t("modules.add.visible")} hint={t("modules.add.visibleHint")} checked={visible} disabled={busy} onChange={setVisible} />
            {kind !== "header" && (
              <>
                <RequirementFields kind={itemKind} value={req} onChange={setReq} disabled={busy} />
                {touched && reqBody === undefined && <p role="alert" className="text-sm text-danger-700">{t("modules.reqPicker.thresholdInvalid")}</p>}
              </>
            )}
          </>
        )}
        {error ? <p role="alert" className="rounded-xl border border-danger-200 bg-danger-50 px-3 py-2 text-sm text-danger-800">{errorText(error)}</p> : null}
      </form>
      {sub === "upload" && (
        <UploadFileDialog open courseId={courseId} folders={[]} onClose={() => setSub(null)} onDone={onFileUploaded} />
      )}
      {sub === "assignment" && (
        <AssignmentEditorDialog open onCreated={onAssignmentCreated} onCancel={() => setSub(null)} />
      )}
    </Dialog>
  );
}

// ---------------------------------------------------------------- Phase 8c S2: put an unsorted target into a module

export interface PlaceTarget {
  kind: "page" | "file" | "assignment";
  id: string;
  title: string;
}

/** "Move to module…" of the Unsorted group (§3.4): pick a module and a position, then `POST …/modules/{mid}/items`. */
export function PlaceInModuleDialog({ open, target, modules, courseId, defaultLang, onPlaced, onClose }: {
  open: boolean;
  target: PlaceTarget;
  modules: ModuleStaffOut[];
  courseId: string;
  defaultLang: Lang;
  onPlaced: (moduleId: string) => void;
  onClose: () => void;
}) {
  const { lang, t } = useTranslation();
  const errorText = useModuleErrorText();
  const live = modules.filter((m) => !m.deleted_at);
  const [to, setTo] = useState(live[0]?.id ?? "");
  const mod = live.find((m) => m.id === to);
  const items = mod ? [...mod.items].sort((a, b) => a.position - b.position) : [];
  const [pos, setPos] = useState("end");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const itemTitle = (i: ItemStaffOut) =>
    pickLocalized(i.title_override, lang, defaultLang) || pickLocalized(i.target?.title, lang, defaultLang) || i.url || t("modules.untitledItem");

  const place = async () => {
    if (!mod) return;
    setBusy(true);
    setError(null);
    try {
      const body: ItemIn = { kind: target.kind, published: true };
      if (target.kind === "page") body.page_id = target.id;
      if (target.kind === "file") body.file_id = target.id;
      if (target.kind === "assignment") body.assignment_id = target.id;
      if (pos !== "end") body.position = Number(pos);
      await addItem(courseId, mod.id, body);
      onPlaced(mod.id);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} busy={busy} size="md" title={t("coursePage.unsorted.placeTitle")} description={target.title}
      footer={(
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t("lms.common.cancel")}</Button>
          <Button onClick={() => void place()} loading={busy} disabled={!mod}>{t("modules.move.submit")}</Button>
        </>
      )}>
      <div className="space-y-4">
        {live.length === 0 ? (
          <p className="text-sm text-slate-700">{t("coursePage.unsorted.noModules")}</p>
        ) : (
          <>
            <Select label={t("modules.move.target")} value={to} disabled={busy} onChange={(e) => { setTo(e.target.value); setPos("end"); }}
              options={live.map((m) => ({ value: m.id, label: pickLocalized(m.title, lang, defaultLang) || t("modules.untitledModule") }))} />
            <Select label={t("coursePage.unsorted.position")} value={pos} disabled={busy} onChange={(e) => setPos(e.target.value)}
              options={[
                ...(items.length > 0 ? [{ value: "1", label: t("coursePage.unsorted.atStart") }] : []),
                ...items.slice(0, -1).map((i, n) => ({ value: String(n + 2), label: t("coursePage.unsorted.after", { title: itemTitle(i) }) })),
                { value: "end", label: t("coursePage.unsorted.atEnd") },
              ]} />
          </>
        )}
        {error ? <p role="alert" className="rounded-xl border border-danger-200 bg-danger-50 px-3 py-2 text-sm text-danger-800">{errorText(error)}</p> : null}
      </div>
    </Dialog>
  );
}
