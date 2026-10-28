"use client";

// Phase 8a S4a (PHASE_8A_DESIGN 8.1, 5.5): Settings -> "Course home": what students see first (modules, a page, or
// assignments and results). Locked template courses (ORT) show the choice disabled with the locked-field note; the
// server refuses the change anyway (409 `template_locked`).
import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { updateCourse } from "@/lib/lms/courses";
import { listPagesForPicker } from "@/lib/lms/modules";
import type { PagePickOut } from "@/lib/lms/modulesTypes";
import { templateUi } from "@/lib/lms/templates";
import type { CourseStaffOut, HomeKind } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button, Select } from "@/components/ui";

const KINDS: HomeKind[] = ["modules", "page", "assignments"];

export function CourseHomeSection({ course }: { course: CourseStaffOut }) {
  const { t } = useTranslation();
  const { setCourse } = useCourse();
  const locked = templateUi(course).locked;
  const [kind, setKind] = useState<HomeKind>(course.home_kind ?? "assignments");
  const [pageId, setPageId] = useState(course.home_page_id ?? "");
  const [pages, setPages] = useState<PagePickOut[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (kind !== "page" || pages) return;
    listPagesForPicker(course.id)
      .then((p) => setPages(p.items.filter((x) => !x.deleted_at)))
      .catch(() => setPages([]));
  }, [kind, pages, course.id]);

  const pageOk = kind !== "page" || !!pageId;
  const save = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!pageOk || locked) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      setCourse(await updateCourse(course.id, { home_kind: kind, home_page_id: kind === "page" ? pageId : null }));
      setSaved(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form id="course-home" onSubmit={(e) => void save(e)} noValidate className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
      <div>
        <h2 className="text-lg font-bold text-slate-900">{t("courses.homeKind.title")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t("courses.homeKind.hint")}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Select label={t("courses.homeKind.label")} value={kind} disabled={busy || locked}
          hint={locked ? t("templates.lockedNote") : t(`courses.homeKind.hints.${kind}`)}
          onChange={(e) => { setKind(e.target.value as HomeKind); setSaved(false); }}
          options={KINDS.map((k) => ({ value: k, label: t(`courses.homeKind.kinds.${k}`) }))} />
        {kind === "page" && !locked && (
          <Select label={t("courses.homeKind.page")} value={pageId} disabled={busy || !pages} placeholder={t("courses.homeKind.choosePage")}
            hint={pages && pages.length === 0 ? t("courses.homeKind.noPages") : t("courses.homeKind.pageHint")}
            onChange={(e) => { setPageId(e.target.value); setSaved(false); }}
            options={(pages ?? []).map((p) => ({
              value: p.id,
              label: `${p.title} (${t(`courses.languages.${p.language}`)})${p.published ? "" : ` · ${t("modules.editor.draft")}`}`,
            }))} />
        )}
      </div>
      {!locked && (
        <>
          <ErrorMessage error={error} />
          <div className="flex items-center gap-3">
            <Button type="submit" size="sm" loading={busy} disabled={!pageOk}>{t("lms.common.save")}</Button>
            {saved && <p role="status" className="text-sm text-success-700">{t("courses.settings.saved")}</p>}
          </div>
        </>
      )}
    </form>
  );
}
