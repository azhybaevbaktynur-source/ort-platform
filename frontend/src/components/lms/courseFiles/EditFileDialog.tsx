"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { updateCourseFile } from "@/lib/lms/courseFiles";
import type { CourseFileStaffOut } from "@/lib/lms/pagesTypes";
import { ContentError } from "@/components/lms/pages/ApiError";
import { Button, Dialog, Input, Switch, toast } from "@/components/ui";

/** Rename, move to another folder and publish / unpublish one file. */
export function EditFileDialog({
  file, courseId, folders, onClose, onDone,
}: { file: CourseFileStaffOut | null; courseId: string; folders: string[]; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [folder, setFolder] = useState("");
  const [published, setPublished] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (file) { setTitle(file.title); setFolder(file.folder); setPublished(file.published); setError(null); }
  }, [file]);

  const submit = async () => {
    if (!file || !title.trim()) return;
    setBusy(true); setError(null);
    try {
      await updateCourseFile(courseId, file.id, { title: title.trim(), folder: folder.trim().replace(/^\/+|\/+$/g, ""), published });
      toast.success(t("courseFiles.saved"));
      onDone();
    } catch (e) { setError(e); } finally { setBusy(false); }
  };

  return (
    <Dialog
      open={!!file} onClose={onClose} busy={busy} title={t("courseFiles.editTitle")}
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={busy}>{t("common.cancel")}</Button>
        <Button onClick={() => void submit()} loading={busy} disabled={!title.trim()}>{t("common.save")}</Button>
      </>}
    >
      <div className="space-y-4">
        <ContentError error={error} />
        <Input label={t("courseFiles.fieldTitle")} value={title} maxLength={300} onChange={(ev) => setTitle(ev.target.value)} />
        <div>
          <Input label={t("courseFiles.fieldFolder")} value={folder} maxLength={200} list="cf-folders-edit" optional
            hint={t("courseFiles.folderHint")} onChange={(ev) => setFolder(ev.target.value)} />
          <datalist id="cf-folders-edit">{folders.map((f) => <option key={f} value={f} />)}</datalist>
        </div>
        <Switch label={t("courseFiles.fieldPublished")} hint={t("courseFiles.publishedHint")} checked={published} onChange={setPublished} />
      </div>
    </Dialog>
  );
}
