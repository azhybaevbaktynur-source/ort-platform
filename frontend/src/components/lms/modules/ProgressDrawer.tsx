"use client";

// Phase 8a S4a (PHASE_8A_DESIGN 8.1): "Student progress": pick one student of the roster, see their modules as the
// student sees them (read-only; `GET _C/modules/progress/{enrollment_id}`, one student per request).
import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { listPeople } from "@/lib/lms/courses";
import { getStudentProgress } from "@/lib/lms/modules";
import type { ModulesStudentOut } from "@/lib/lms/modulesTypes";
import type { RosterEntryOut } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { Dialog, ErrorState, LoadingState, Select } from "@/components/ui";
import { ModuleList } from "./StudentModulesView";
import { useModuleErrorText } from "./moduleUi";

export function ProgressDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const { course } = useCourse();
  const errorText = useModuleErrorText();
  const [students, setStudents] = useState<RosterEntryOut[] | null>(null);
  const [rosterError, setRosterError] = useState<unknown>(null);
  const [picked, setPicked] = useState("");
  const [data, setData] = useState<ModulesStudentOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listPeople(course.id, { role: "student", state: "active", limit: 100 })
      .then((p) => setStudents(p.items as RosterEntryOut[]))
      .catch((e) => { setRosterError(e); setStudents([]); });
  }, [course.id]);

  useEffect(() => {
    if (!picked) { setData(null); return; }
    let live = true;
    setLoading(true);
    setError(null);
    getStudentProgress(course.id, picked)
      .then((d) => { if (live) setData({ modules: d.modules ?? [], up_next: d.up_next ?? null }); })
      .catch((e) => { if (live) setError(e); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [course.id, picked]);

  return (
    <Dialog open={open} onClose={onClose} size="lg" title={t("modules.progress.title")} description={t("modules.progress.hint")}>
      <div className="space-y-4">
        {rosterError ? <ErrorState variant="inline" message={errorText(rosterError)} /> : null}
        {!students ? <LoadingState rows={1} /> : students.length === 0 ? (
          <p className="rounded-xl bg-slate-50 px-3 py-3 text-sm text-slate-700">{t("modules.progress.noStudents")}</p>
        ) : (
          <Select label={t("modules.progress.student")} value={picked} onChange={(e) => setPicked(e.target.value)}
            placeholder={t("modules.progress.choose")}
            options={students.map((s) => ({ value: s.enrollment_id, label: s.user.display_name || s.user.email }))} />
        )}
        {error ? <ErrorState variant="inline" message={errorText(error)} /> : null}
        {loading && !data ? <LoadingState rows={2} /> : null}
        {data && (data.modules.length === 0
          ? <p className="text-sm text-slate-700">{t("modules.progress.empty")}</p>
          : <ModuleList data={data} mode="progress" />)}
      </div>
    </Dialog>
  );
}
