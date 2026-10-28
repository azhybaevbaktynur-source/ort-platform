"use client";

import React, { useEffect, useRef, useState } from "react";
import { FileUp } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { uploadCourseFile } from "@/lib/lms/courseFiles";
import { FILE_MAX_BYTES } from "@/lib/lms/pagesTypes";
import { ContentError } from "@/components/lms/pages/ApiError";
import { Button, Dialog, Input, Switch, toast } from "@/components/ui";

/** Upload a PDF (max 10 MB) into a folder; errors (quota, storage full, size, type) are translated. */
export function UploadFileDialog({
  open, courseId, folders, onClose, onDone,
}: { open: boolean; courseId: string; folders: string[]; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [folder, setFolder] = useState("");
  const [published, setPublished] = useState(true);
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  useEffect(() => {
    if (open) { setFile(null); setTitle(""); setFolder(""); setPublished(true); setProgress(0); setError(null); setFileError(null); }
  }, [open]);

  const choose = (f: File | undefined) => {
    setError(null);
    if (!f) { setFile(null); return; }
    const isPdf = f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) { setFile(null); setFileError(t("courseFiles.errors.notPdf")); return; }
    if (f.size > FILE_MAX_BYTES) { setFile(null); setFileError(t("courseFiles.errors.tooBig")); return; }
    setFileError(null);
    setFile(f);
    if (!title.trim()) setTitle(f.name.replace(/\.pdf$/i, ""));
  };

  const submit = async () => {
    if (!file || !title.trim()) return;
    setBusy(true); setError(null); setProgress(0);
    try {
      await uploadCourseFile(courseId, { file, folder: folder.trim().replace(/^\/+|\/+$/g, ""), title: title.trim(), published }, setProgress);
      toast.success(t("courseFiles.uploaded"));
      onDone();
    } catch (e) { setError(e); } finally { setBusy(false); }
  };

  return (
    <Dialog
      open={open} onClose={onClose} busy={busy} title={t("courseFiles.uploadTitle")} description={t("courseFiles.uploadHint")}
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={busy}>{t("common.cancel")}</Button>
        <Button onClick={() => void submit()} loading={busy} disabled={!file || !title.trim()}>{t("courseFiles.upload")}</Button>
      </>}
    >
      <div className="space-y-4">
        <ContentError error={error} />
        <div>
          <label htmlFor="cf-file" className="text-sm font-medium text-slate-800">{t("courseFiles.fieldFile")}</label>
          {/* 8a UX (minor 9): the native input is visually hidden; a styled button opens it and the chosen name shows */}
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            <input
              id="cf-file" ref={fileRef} type="file" accept="application/pdf,.pdf" disabled={busy}
              aria-describedby={file ? "cf-file-name" : undefined}
              onChange={(ev) => choose(ev.target.files?.[0])}
              className="peer sr-only"
            />
            <label htmlFor="cf-file" aria-hidden="true"
              className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 shadow-sm hover:bg-slate-50 peer-focus-visible:ring-2 peer-focus-visible:ring-brand-600 peer-focus-visible:ring-offset-2 peer-disabled:cursor-not-allowed peer-disabled:opacity-60">
              <FileUp aria-hidden="true" className="h-4 w-4" />{t("courseFiles.chooseFile")}
            </label>
            {file && <span id="cf-file-name" className="min-w-0 break-all text-sm text-slate-700">{file.name}</span>}
          </div>
          {fileError && <p role="alert" className="mt-1 text-sm text-danger-700">{fileError}</p>}
        </div>
        <Input label={t("courseFiles.fieldTitle")} value={title} maxLength={300} onChange={(ev) => setTitle(ev.target.value)} />
        <div>
          <Input label={t("courseFiles.fieldFolder")} value={folder} maxLength={200} list="cf-folders" optional
            hint={t("courseFiles.folderHint")} onChange={(ev) => setFolder(ev.target.value)} />
          <datalist id="cf-folders">{folders.map((f) => <option key={f} value={f} />)}</datalist>
        </div>
        <Switch label={t("courseFiles.fieldPublished")} hint={t("courseFiles.publishedHint")} checked={published} onChange={setPublished} />
        {busy && (
          <div role="progressbar" aria-label={t("courseFiles.uploading")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)} className="h-2 overflow-hidden rounded-full bg-slate-200">
            <div className="h-full bg-brand-600" style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
        )}
      </div>
    </Dialog>
  );
}
