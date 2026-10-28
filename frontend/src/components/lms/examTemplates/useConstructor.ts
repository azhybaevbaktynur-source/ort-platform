"use client";

// Phase 8b S4: the constructor's state model (PHASE_8B_DESIGN 9.2). One `SpecDraft` is the source of truth; it
// autosaves 1.5 s after the last change, only when the client pre-check passes, through the strict 7b PATCH
// (`draft_rev`). Invalid or unsent drafts stay local and are mirrored to sessionStorage (offered back on reload);
// a `draft_conflict` opens the 7c conflict dialog (take theirs / keep mine).
import { useCallback, useEffect, useRef, useState } from "react";
import { getExamTemplate, getExamTemplateVersion, patchExamTemplate, templateDraftStorageKey } from "@/lib/lms/examTemplates";
import type { ExamTemplateOut, ExamTemplatePatchIn, ExamTemplateSpec, SpecIssue } from "@/lib/lms/examTemplateTypes";
import { cleanLocalized } from "@/lib/lms/localized";
import { LMS_LANGS, type LocalizedText } from "@/lib/lms/types";
import { draftOf, precheckDraft, specOf, type SpecDraft } from "./specDraft";
import { specIssuesOf } from "./ui";

export const AUTOSAVE_MS = 1500;

export type SaveState = "idle" | "dirty" | "saving" | "saved" | "invalid" | "conflict" | "error";

export interface Meta {
  title: LocalizedText;
  description: LocalizedText;
}

interface Mirror {
  title: LocalizedText;
  description: LocalizedText;
  spec: ExamTemplateSpec;
  at: string;
}

type Body = Required<Pick<ExamTemplatePatchIn, "title" | "description" | "draft_spec">>;

function bodyOf(d: SpecDraft, m: Meta): Body {
  const description = cleanLocalized(m.description, LMS_LANGS);
  return {
    title: cleanLocalized(m.title, LMS_LANGS),
    description: Object.keys(description).length ? description : null,
    draft_spec: specOf(d),
  };
}

function readMirror(id: string): Mirror | null {
  try {
    const raw = window.sessionStorage.getItem(templateDraftStorageKey(id));
    if (!raw) return null;
    const m = JSON.parse(raw) as Mirror;
    return m && m.spec && Array.isArray(m.spec.sections) ? m : null;
  } catch {
    return null;
  }
}
function writeMirror(id: string, body: Body) {
  try {
    const m: Mirror = { title: body.title, description: body.description ?? {}, spec: body.draft_spec as ExamTemplateSpec, at: new Date().toISOString() };
    window.sessionStorage.setItem(templateDraftStorageKey(id), JSON.stringify(m));
  } catch { /* storage full or blocked: the draft only lives in memory */ }
}
function clearMirror(id: string) {
  try { window.sessionStorage.removeItem(templateDraftStorageKey(id)); } catch { /* ignore */ }
}

export function useConstructor(templateId: string, opts: { readOnly: (t: ExamTemplateOut) => boolean }) {
  const [tpl, setTpl] = useState<ExamTemplateOut | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [draft, setDraft] = useState<SpecDraft | null>(null);
  const [meta, setMetaState] = useState<Meta>({ title: {}, description: {} });
  const [fromVersion, setFromVersion] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [serverIssues, setServerIssues] = useState<SpecIssue[]>([]);
  const [clientIssues, setClientIssues] = useState<SpecIssue[]>([]);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [restore, setRestore] = useState<Mirror | null>(null);
  const [conflictBusy, setConflictBusy] = useState(false);

  const draftRef = useRef<SpecDraft | null>(null);
  const metaRef = useRef<Meta>(meta);
  const revRef = useRef(0);
  const savedJson = useRef("");
  const inflight = useRef<Promise<boolean> | null>(null);
  const conflictRef = useRef(false);
  const readOnlyRef = useRef(true);
  draftRef.current = draft;
  metaRef.current = meta;
  const readOnlyOf = opts.readOnly;

  const seed = useCallback(async (x: ExamTemplateOut, { offerRestore }: { offerRestore: boolean }) => {
    let spec: ExamTemplateSpec | null = x.draft_spec ?? null;
    let from: number | null = null;
    if (!spec && x.current_version_no != null) {
      spec = x.current_spec ?? (await getExamTemplateVersion(x.id, x.current_version_no)).spec;
      from = x.current_version_no;
    }
    const d = draftOf(spec ?? { sections: [] });
    const m: Meta = { title: { ...(x.title ?? {}) }, description: { ...(x.description ?? {}) } };
    revRef.current = x.draft_rev ?? 1;
    savedJson.current = JSON.stringify(bodyOf(d, m));
    conflictRef.current = false;
    readOnlyRef.current = readOnlyOf(x);
    draftRef.current = d;
    metaRef.current = m;
    setTpl(x);
    setDraft(d);
    setMetaState(m);
    setFromVersion(from);
    setServerIssues([]);
    setClientIssues([]);
    setSaveError(null);
    setSaveState("idle");
    const stored = offerRestore && !readOnlyRef.current ? readMirror(x.id) : null;
    const storedJson = stored ? JSON.stringify(bodyOf(draftOf(stored.spec), { title: stored.title, description: stored.description })) : "";
    if (stored && storedJson !== savedJson.current) setRestore(stored);
    else { setRestore(null); if (!offerRestore) clearMirror(x.id); }
  }, [readOnlyOf]);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      await seed(await getExamTemplate(templateId), { offerRestore: true });
    } catch (e) {
      setLoadError(e);
    }
  }, [templateId, seed]);

  useEffect(() => { setTpl(null); void load(); }, [load]);

  /** Send the current draft when it differs from the last saved one. Resolves true when the server has it. */
  const flush = useCallback(async (): Promise<boolean> => {
    while (inflight.current) await inflight.current;
    const d = draftRef.current;
    if (!d || readOnlyRef.current || conflictRef.current) return !d ? false : !conflictRef.current;
    const m = metaRef.current;
    const body = bodyOf(d, m);
    const json = JSON.stringify(body);
    if (json === savedJson.current) return true;
    const pre = precheckDraft(d);
    if (Object.keys(body.title).length === 0) pre.unshift({ loc: ["title"], msg: "", type: "title_required" });
    setClientIssues(pre);
    if (pre.length) { setSaveState("invalid"); return false; }
    setSaveState("saving");
    setSaveError(null);
    const run = (async () => {
      try {
        const out = await patchExamTemplate(templateId, { draft_rev: revRef.current, ...body });
        revRef.current = out.draft_rev ?? revRef.current + 1;
        savedJson.current = json;
        setTpl(out);
        setServerIssues([]);
        const now = draftRef.current ? JSON.stringify(bodyOf(draftRef.current, metaRef.current)) : json;
        if (now === json) { setSaveState("saved"); clearMirror(templateId); } else setSaveState("dirty");
        return true;
      } catch (e) {
        const code = (e as { code?: string }).code;
        if (code === "draft_conflict") {
          conflictRef.current = true;
          setSaveState("conflict");
        } else if (code === "spec_invalid") {
          setServerIssues(specIssuesOf(e));
          setSaveState("invalid");
        } else {
          setSaveError(e);
          setSaveState("error");
        }
        return false;
      }
    })();
    inflight.current = run;
    try { return await run; } finally { inflight.current = null; }
  }, [templateId]);

  // Debounced autosave + sessionStorage mirror after every change.
  useEffect(() => {
    if (!draft || !tpl || readOnlyRef.current) return;
    const body = bodyOf(draft, meta);
    if (JSON.stringify(body) === savedJson.current) return;
    writeMirror(templateId, body);
    if (conflictRef.current) return;
    setSaveState((s) => (s === "saving" ? s : "dirty"));
    const timer = setTimeout(() => { void flush(); }, AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [draft, meta, tpl, templateId, flush]);

  const update = useCallback((fn: (d: SpecDraft) => SpecDraft) => {
    setDraft((d) => (d ? fn(d) : d));
  }, []);
  const setMeta = useCallback((patch: Partial<Meta>) => setMetaState((m) => ({ ...m, ...patch })), []);

  /** Replace the whole template from a server payload (after publish, lock, ...); unsaved edits are dropped. */
  const replace = useCallback((x: ExamTemplateOut) => seed(x, { offerRestore: false }), [seed]);

  const acceptRestore = useCallback(() => {
    if (!restore) return;
    setDraft(draftOf(restore.spec));
    setMetaState({ title: { ...restore.title }, description: { ...restore.description } });
    setRestore(null);
  }, [restore]);
  const discardRestore = useCallback(() => {
    clearMirror(templateId);
    setRestore(null);
  }, [templateId]);

  /** 7c conflict dialog, "keep mine": take the newer `draft_rev` and send this draft over it. */
  const keepMine = useCallback(async () => {
    setConflictBusy(true);
    try {
      const fresh = await getExamTemplate(templateId);
      revRef.current = fresh.draft_rev ?? revRef.current;
      setTpl(fresh);
      conflictRef.current = false;
      setSaveState("dirty");
      await flush();
    } catch (e) {
      setSaveError(e);
    } finally {
      setConflictBusy(false);
    }
  }, [templateId, flush]);
  /** "Take theirs": reload the stored draft; local edits are dropped. */
  const takeTheirs = useCallback(async () => {
    setConflictBusy(true);
    try {
      clearMirror(templateId);
      await seed(await getExamTemplate(templateId), { offerRestore: false });
    } catch (e) {
      setSaveError(e);
    } finally {
      setConflictBusy(false);
    }
  }, [templateId, seed]);

  const issues = clientIssues.length ? clientIssues : serverIssues;
  return {
    tpl, loadError, load, draft, meta, update, setMeta, fromVersion, saveState, issues, saveError,
    flush, replace, restore, acceptRestore, discardRestore, keepMine, takeTheirs, conflictBusy,
    draftRev: tpl?.draft_rev ?? 0,
  };
}

export type ConstructorState = ReturnType<typeof useConstructor>;
