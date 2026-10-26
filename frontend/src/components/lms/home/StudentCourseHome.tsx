"use client";

// Phase 6b S6b (UX S5): a student's course home answers "what do I do next here?": the next assessment with
// the page's one primary button, the latest released result, then the description. No teacher states, no roadmap
// text; "Leave course" is a quiet link at the bottom.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { leaveCourse } from "@/lib/lms/courses";
// --- Phase 7a S5: the course home reads assignments ---
import { listAssignments } from "@/lib/lms/assignments";
import type { AssignmentStudentOut } from "@/lib/lms/assignmentTypes";
import { templateUi } from "@/lib/lms/templates";
import { StudentAssignmentCard } from "@/components/lms/assignments/StudentAssignmentCard";
import { primaryAssignmentId, sortForStudent, studentAssignmentView } from "@/components/lms/assignments/studentAssignment";
// --- Phase 7a S5 end ---
import { getMyGrades } from "@/lib/lms/grading";
import type { MyGradeOut } from "@/lib/lms/gradingTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { parseApiDate } from "@/lib/format";
import { useCourse } from "@/components/lms/CourseContext";
import { Button, Card, ConfirmDialog, DescriptionList, ErrorState, LinkButton, LoadingState } from "@/components/ui";
import { useGradeText } from "@/components/lms/results/GradeBadge";
import { fmtShortDateTime } from "./format";
import { useErrorText } from "./useErrorText";

export function StudentCourseHome() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { course } = useCourse();
  const errorText = useErrorText();
  const gradeText = useGradeText();
  const base = `/${lang}/courses/${course.id}`;
  const [items, setItems] = useState<AssignmentStudentOut[] | null>(null); // Phase 7a S5: assignments
  const [grades, setGrades] = useState<MyGradeOut[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [leaving, setLeaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [leaveError, setLeaveError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [page, mine] = await Promise.all([
        listAssignments(course.id, { limit: 50 }),
        getMyGrades(course.id).catch(() => null),
      ]);
      setItems(page.items as AssignmentStudentOut[]);
      setGrades(mine?.items ?? []);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id]);
  useEffect(() => { void load(); }, [load]);

  // Phase 7a S5: the next assignment (a running quiz first, then the nearest one to start or hand in)
  const next = useMemo(() => {
    if (!items) return null;
    const now = Date.now();
    const readOnly = !!course.my_enrollment.read_only;
    const rows = sortForStudent(items).map((a) => ({ a, v: studentAssignmentView(a, now, readOnly) }));
    const id = primaryAssignmentId(rows);
    return rows.find((r) => r.a.id === id) ?? (readOnly ? rows[0] ?? null : null);
  }, [items, course.my_enrollment.read_only]);

  const latest = useMemo(() => {
    const graded = grades.filter((g) => g.state === "graded");
    if (graded.length === 0) return null;
    const ts = (g: MyGradeOut) => parseApiDate(g.released_at)?.getTime() ?? 0;
    return graded.reduce((best, g) => (ts(g) > ts(best) ? g : best));
  }, [grades]);

  const leave = async () => {
    setBusy(true);
    setLeaveError(null);
    try {
      await leaveCourse(course.id);
      router.push(`/${lang}/courses`);
    } catch (e) {
      setLeaveError(e);
      setBusy(false);
    }
  };

  const description = pickLocalized(course.description, lang, course.default_language);
  const title = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");
  // S11a, F1: a locked platform template (ORT) has no teacher to name; say who runs it instead.
  const platformRun = !!course.template?.locked;
  const teacher = platformRun ? t("courses.home.providerPlatform") : course.owner_display_name || "—";

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      {course.status === "concluded" && (
        <p role="status" className="rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-base leading-6 text-slate-700 sm:text-sm">{t("courses.home.concludedNotice")}</p>
      )}

      <section aria-labelledby="course-next" className="space-y-3">
        <h2 id="course-next" className="text-lg font-semibold leading-7 text-slate-900">{t("home.course.nextTitle")}</h2>
        {error && !items ? (
          <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load()} retrying={loading} />
        ) : !items ? (
          <LoadingState rows={1} />
        ) : next ? (
          <StudentAssignmentCard as="div" a={next.a} v={next.v} base={base} primary ort={templateUi(course).key === "ort"}
            title={pickLocalized(next.a.title, lang, course.default_language) || t("assignments.untitled")} />
        ) : (
          <Card>
            <p className="text-base leading-6 text-slate-700">{items.length ? t("home.next.empty") : t("home.course.noAssessments")}</p>
            {items.length > 0 && (
              <div className="mt-3"><LinkButton variant="secondary" href={`${base}/assignments`}>{t("home.course.allAssessments")}</LinkButton></div>
            )}
          </Card>
        )}
      </section>

      {latest && (
        <Card title={t("home.course.latestTitle")} headingLevel={2}>
          <p className="break-words text-base font-semibold leading-6 text-slate-900">{pickLocalized(latest.title, lang, course.default_language) || t("assessments.untitled")}</p>
          <p className="mt-1 text-2xl font-bold leading-8 text-slate-900">{gradeText(latest, latest.scheme_type ?? undefined, latest.labels) || "—"}</p>
          {latest.released_at && <p className="text-sm leading-6 text-slate-600">{fmtShortDateTime(latest.released_at, lang)}</p>}
          <div className="mt-3 flex flex-col gap-2 sm:flex-row [&>*]:w-full sm:[&>*]:w-auto">
            {latest.kept_attempt_id && <LinkButton variant="secondary" href={`${base}/attempts/${latest.kept_attempt_id}/result`}>{t("home.action.result")}</LinkButton>}
            <LinkButton variant="link" href={`${base}/grades`}>{t("home.course.allGrades")}</LinkButton>
          </div>
        </Card>
      )}

      <Card title={t("courses.home.about")} headingLevel={2}>
        <p className="whitespace-pre-line break-words text-base leading-6 text-slate-800">{description || t("courses.home.noDescription")}</p>
        <DescriptionList className="mt-5" twoColumns items={[
          { key: "teacher", term: platformRun ? t("courses.home.provider") : t("courses.home.owner"), description: teacher },
          { key: "langs", term: t("courses.home.languages"), description: course.languages.map((l) => t(`courses.languages.${l}`)).join(", ") },
        ]} />
      </Card>

      {!course.my_enrollment.read_only && <div className="border-t border-slate-200 pt-4">
        <Button variant="link" className="text-slate-600 hover:text-danger-700" leftIcon={<LogOut aria-hidden="true" className="h-4 w-4" />} onClick={() => setLeaving(true)}>
          {t("courses.home.leave")}
        </Button>
      </div>}
      <ConfirmDialog open={leaving} tone="danger" busy={busy} error={leaveError ? errorText(leaveError) : undefined}
        title={t("courses.home.leaveTitle")} object={title} effect={t("courses.home.leaveBody")}
        confirmLabel={t("courses.home.leave")} onConfirm={() => void leave()} onCancel={() => setLeaving(false)} />
    </div>
  );
}
