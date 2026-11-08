"use client";

// FB8-5 S3 (STAFF_UX_AUDIT 5): Danger zone, owner only (the page hides the tab for others; the server refuses them):
// transfer ownership to another teacher of the course, delete the course (to the trash). Both confirmed.
import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { deleteCourse, listPeople, transferOwnership } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import type { CourseStaffOut, RosterEntryOut } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button, Card, ConfirmDialog, Select } from "@/components/ui";
import { SectionLayout, useSave } from "./shared";

export function DangerSection({ course, onSaved }: { course: CourseStaffOut; onSaved: (c: CourseStaffOut) => void }) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const s = useSave();
  const [teachers, setTeachers] = useState<RosterEntryOut[]>([]);
  const [newOwner, setNewOwner] = useState("");
  const [confirm, setConfirm] = useState<null | "delete" | "transfer">(null);

  useEffect(() => {
    listPeople(course.id, { role: "teacher", state: "active", limit: 100 })
      .then((p) => setTeachers((p.items as RosterEntryOut[]).filter((e) => !e.is_owner)))
      .catch(() => setTeachers([]));
  }, [course.id]);

  const courseName = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");
  const owner = teachers.find((e) => e.user.id === newOwner);
  const doConfirm = async () => {
    if (confirm === "delete") {
      if (await s.run(async () => { await deleteCourse(course.id); router.push(`/${lang}/courses`); })) setConfirm(null);
    } else if (confirm === "transfer") {
      if (await s.run(async () => onSaved(await transferOwnership(course.id, newOwner)))) setConfirm(null);
    }
  };

  return (
    <SectionLayout>
      <Card title={<span className="text-danger-700">{t("courses.settings.danger")}</span>} className="border-danger-200">
        <div className="space-y-6">
          <div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <Select id="s-owner" containerClassName="min-w-0 sm:w-80" label={t("courses.settings.newOwner")} value={newOwner}
                onChange={(e) => setNewOwner(e.target.value)} hint={t("courses.settings.transferHint")}
                placeholder={teachers.length ? t("courses.settings.chooseTeacher") : t("courses.settings.noOtherTeachers")}
                options={teachers.map((e) => ({ value: e.user.id, label: e.user.display_name || e.user.email }))} />
              <Button size="sm" variant="dangerOutline" disabled={!newOwner} className="sm:mb-6"
                onClick={() => { s.setError(null); setConfirm("transfer"); }}>
                {t("courses.settings.transfer")}
              </Button>
            </div>
          </div>
          <div className="border-t border-slate-100 pt-5">
            <p className="mb-3 text-sm leading-6 text-slate-600">{t("courses.settings.deleteBody")}</p>
            <Button size="sm" variant="danger" onClick={() => { s.setError(null); setConfirm("delete"); }}>
              {t("courses.settings.delete")}
            </Button>
          </div>
        </div>
      </Card>
      {confirm && (
        <ConfirmDialog open tone="danger" busy={s.busy}
          title={t(confirm === "delete" ? "courses.settings.deleteTitle" : "courses.settings.transferTitle")}
          object={confirm === "transfer" && owner ? `${courseName} → ${owner.user.display_name || owner.user.email}` : courseName}
          effect={t(confirm === "delete" ? "courses.settings.deleteBody" : "courses.settings.transferBody")}
          error={s.error ? <ErrorMessage error={s.error} /> : undefined}
          confirmLabel={t(confirm === "delete" ? "courses.settings.delete" : "courses.settings.transfer")}
          onConfirm={() => void doConfirm()} onCancel={() => { setConfirm(null); s.setError(null); }} />
      )}
    </SectionLayout>
  );
}
