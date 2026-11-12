"use client";

// Student UI U4 (docs/phases/STUDENT_UI_DESIGN.md §3.2): the Тесты page of an exam-prep course, `/courses/{c}/tests`.
// Title "Тесты · N", filter chips (sources from the server, statuses over the loaded cards), then the library as cards
// in a 3 / 2 / 1 grid: status pill, title, questions and duration, best score and one action. Every card opens the
// unchanged lobby; a paid test without a pass shows a "Платный" lock pill, a blurred score and "Открыть доступ"
// (/pro; the sidebar's gold pill is the page-wide way). Two reads in parallel: the exam-prep page (sources, total)
// and the paginated library.
// U9 (STUDENT_UI_REVIEW 2, 7, 8, 10): no score tiles (the numbers live on the home and in Аналитика), no breadcrumbs
// and no "Покинуть курс" (the shell navigates; leaving is in its exam sheet), one lock signal pair on a paid card
// ("Платный" chip and the gold pill); one blue primary (owner 2026-11-07: no violet accent, gold is the only accent).
import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ClipboardList, Clock, ListChecks, Lock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { inCourseSpace, templateUi } from "@/lib/lms/templates";
import { listAssignments } from "@/lib/lms/assignments"; // step 3a S2
import type { AssignmentStudentOut } from "@/lib/lms/assignmentTypes";
import {
  SOURCE_OTHER, listExamLibrary, wholeNumber, type LibraryCardOut, type LibraryStatus,
} from "@/lib/lms/examPrep";
import { useExamPrep } from "@/lib/lms/pageData"; // PERFORMANCE_AUDIT S3
import { useCourse } from "@/components/lms/CourseContext";
import {
  Badge, EmptyState, ErrorState, GoldPill, LinkButton, LockOverlay, Pagination, Skeleton, cn, focusRing, type BadgeTone,
} from "@/components/ui";
import { StudentPageHeader } from "@/components/lms/student/StudentPageHeader";
import { fmtDuration } from "@/components/lms/home/format";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { ProCallout } from "@/components/lms/access/ProCallout"; // step 3a S2
import { PracticeList } from "@/components/lms/practice/PracticeList"; // step 3a S2 (D6)
import { StudentAssignmentCard } from "@/components/lms/assignments/StudentAssignmentCard";
import { useAssignmentErrorText } from "@/components/lms/assignments/assignmentUi";
import { primaryAssignmentId, sortForStudent, studentAssignmentView } from "@/components/lms/assignments/studentAssignment";

const STATUSES: LibraryStatus[] = ["not_started", "in_progress", "done"];
const STATUS_TONE: Record<LibraryStatus, BadgeTone> = { not_started: "neutral", in_progress: "info", done: "success" };
const GRID = "grid gap-4 md:grid-cols-2 xl:grid-cols-3";
const PAGE_SIZE = 24;

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={active} onClick={onClick}
      className={cn("inline-flex min-h-11 max-w-full items-center rounded-full border px-4 text-sm font-medium leading-5 transition-colors sm:min-h-9",
        focusRing,
        active ? "border-brand-600 bg-brand-600 text-white" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50")}>
      <span className="truncate">{children}</span>
    </button>
  );
}

/** The score block of a card; for a locked card a neutral placeholder under the blur (no real number). */
function ScoreArea({ card }: { card: LibraryCardOut }) {
  const { t } = useTranslation();
  const best = card.locked ? null : wholeNumber(card.best_value);
  const max = wholeNumber(card.scale_max);
  const box = "flex min-h-[5.5rem] flex-col justify-center rounded-xl bg-slate-50 px-4 py-3";
  if (card.locked) {
    return (
      <div className={box}>
        <span className="text-sm text-slate-600">{t("examPrep.library.best")}</span>
        <span className="text-3xl font-bold leading-9 tabular-nums text-slate-900">—</span>
      </div>
    );
  }
  if (best !== null) {
    return (
      <div className={box}>
        <span className="text-sm leading-5 text-slate-600">{t("examPrep.library.best")}</span>
        <p className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-3xl font-bold leading-9 tabular-nums text-slate-900">{best}</span>
          {max !== null && <span className="text-sm text-slate-600">{t("examPrep.goal.outOf", { max })}</span>}
        </p>
      </div>
    );
  }
  if (card.best_percent !== null) {
    return (
      <div className={box}>
        <span className="text-sm leading-5 text-slate-600">{t("examPrep.library.bestPercent")}</span>
        <span className="text-3xl font-bold leading-9 tabular-nums text-slate-900">{Math.round(card.best_percent)}%</span>
      </div>
    );
  }
  return (
    <div className={box}>
      <span className="text-sm leading-5 text-slate-600">{t("examPrep.library.best")}</span>
      <p className="mt-1 text-base font-medium leading-6 text-slate-700">{card.status === "done" ? t("examPrep.library.pending") : t("examPrep.tests.noScore")}</p>
    </div>
  );
}

function TestCard({ card, lobby, primary }: { card: LibraryCardOut; lobby: string; primary: boolean }) {
  const { lang, t } = useTranslation();
  const titleId = useId();
  const title = pickLocalized(card.title, lang) || t("assessments.untitled");
  const duration = fmtDuration(card.time_limit_s, t);
  let action: React.ReactNode;
  if (card.locked) {
    action = <GoldPill href={`/${lang}/pro`} icon={<Lock />} block className="justify-center">{t("examPrep.tests.unlock")}</GoldPill>;
  } else if (card.status === "done") {
    action = <LinkButton href={lobby} variant="secondary" fullWidth aria-describedby={titleId}>{t("examPrep.tests.result")}</LinkButton>;
  } else {
    action = (
      <LinkButton href={lobby} variant={primary ? "primary" : "secondary"} fullWidth aria-describedby={titleId}>
        {card.status === "in_progress" ? t("examPrep.tests.resume") : t("examPrep.tests.start")}
      </LinkButton>
    );
  }
  return (
    <li className="flex min-w-0 flex-col gap-3 rounded-card border border-slate-200 bg-white p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        {!(card.locked && card.status === "not_started") && <Badge tone={STATUS_TONE[card.status]}>{t(`examPrep.library.status.${card.status}`)}</Badge>}
        {card.locked && (
          <Badge className="border-gold-300 bg-gold-100 text-gold-900" icon={<Lock aria-hidden="true" />}>{t("access.paid")}</Badge>
        )}
      </div>
      <h2 id={titleId} className="break-words text-base font-semibold leading-6 text-slate-900">{title}</h2>
      <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm leading-5 text-slate-600">
        <span className="inline-flex items-center gap-1.5"><ListChecks aria-hidden="true" className="h-4 w-4" />{t("home.questions", { n: card.item_count, count: card.item_count })}</span>
        {duration && <span className="inline-flex items-center gap-1.5"><Clock aria-hidden="true" className="h-4 w-4" />{duration}</span>}
      </p>
      <div className="mt-auto space-y-3">
        <LockOverlay locked={card.locked} className="min-h-0 rounded-xl">
          <ScoreArea card={card} />
        </LockOverlay>
        {action}
      </div>
    </li>
  );
}

function TestsSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-live="polite" className="space-y-6">
      <span className="sr-only">{t("ui.loading")}</span>
      <div aria-hidden="true" className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="flex flex-wrap gap-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-9 w-24 rounded-full" />)}</div>
        <div className={GRID}>{[0, 1, 2].map((i) => <Skeleton key={i} className="h-72 w-full rounded-card" />)}</div>
      </div>
    </div>
  );
}

function TestsLibrary() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const errorText = useErrorText();
  const headingId = useId();
  const base = `/${lang}/courses/${course.id}`;

  // the exam-prep page: sources and total. PERFORMANCE_AUDIT S3: through the SWR cache, so the "Начало работы"
  // checklist reading the same answer sends no second request
  const { data: meta, error: metaError, refresh: refreshMeta } = useExamPrep(course.id);

  // the library, paginated; the source filter is the server's, the status filter applies to the loaded cards
  const [source, setSource] = useState<string | null>(null);
  const [status, setStatus] = useState<LibraryStatus | null>(null);
  const [items, setItems] = useState<LibraryCardOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const seq = useRef(0);
  const load = useCallback(async (next?: string | null) => {
    const mine = ++seq.current; // a newer filter wins over a slower older page
    setLoading(true);
    setError(null);
    try {
      const page = await listExamLibrary(course.id, { source, cursor: next, limit: PAGE_SIZE });
      if (mine !== seq.current) return;
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      if (mine === seq.current) setError(e);
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [course.id, source]);
  useEffect(() => { void load(); }, [load]);

  // PERFORMANCE_AUDIT S3: no page skeleton: the header and the status chips are drawn at once, the cards' place
  // holds skeletons until the library answers ("Тесты" becomes "Тесты · N" with the exam-prep answer)
  const sources = meta?.sources ?? [];
  const shown = status ? items.filter((c) => c.status === status) : items;
  // §5.1 e: one primary button per screen, on the test to continue (else the first not started); the rest secondary
  const open = shown.filter((c) => !c.locked);
  const primaryId = (open.find((c) => c.status === "in_progress") ?? open.find((c) => c.status === "not_started"))?.id ?? null;
  const title = meta ? t("examPrep.tests.heading", { count: meta.library_total }) : t("examPrep.library.title");

  return (
    <div className="space-y-6">
      <section aria-labelledby={headingId} className="min-w-0 space-y-5">
        {/* step 3a S2: the compact course header names the course; the Pro bar goes first under the tabs (§3.5) */}
        {meta?.needs_pass && <ProCallout variant="tests" />}
        <StudentPageHeader id={headingId} title={title} />

        {metaError && !meta ? <ErrorState variant="inline" message={errorText(metaError)} onRetry={() => void refreshMeta()} /> : null}

        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {sources.length > 1 && (
            <div role="group" aria-label={t("examPrep.library.filter")} className="flex min-w-0 flex-wrap gap-2">
              <Chip active={source === null} onClick={() => setSource(null)}>{t("examPrep.library.all")}</Chip>
              {sources.map((s) => {
                const key = s.module_id ?? SOURCE_OTHER;
                return (
                  <Chip key={key} active={source === key} onClick={() => setSource(key)}>
                    {s.module_id ? pickLocalized(s.title, lang) || t("examPrep.library.other") : t("examPrep.library.other")}
                  </Chip>
                );
              })}
            </div>
          )}
          {sources.length > 1 && <span aria-hidden="true" className="hidden h-6 w-px bg-slate-200 sm:block" />}
          <div role="group" aria-label={t("examPrep.tests.statusFilter")} className="flex min-w-0 flex-wrap gap-2">
            <Chip active={status === null} onClick={() => setStatus(null)}>{t("examPrep.tests.allStatuses")}</Chip>
            {STATUSES.map((s) => (
              <Chip key={s} active={status === s} onClick={() => setStatus(s)}>{t(`examPrep.library.status.${s}`)}</Chip>
            ))}
          </div>
        </div>

        {error && items.length === 0 ? <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} /> : null}
        {loading && items.length === 0 && !error && (
          <div role="status" aria-live="polite">
            <span className="sr-only">{t("ui.loading")}</span>
            <div aria-hidden="true" className={GRID}>{[0, 1, 2].map((i) => <Skeleton key={i} className="h-72 w-full rounded-card" />)}</div>
          </div>
        )}
        {!loading && !error && items.length === 0 && (
          <EmptyState mascot="reading" title={source ? t("examPrep.library.emptyFilter") : t("examPrep.library.empty")} />
        )}
        {items.length > 0 && shown.length === 0 && (
          <EmptyState mascot="thinking" title={t("examPrep.tests.emptyStatus")} />
        )}
        {shown.length > 0 && (
          <ul className={GRID} aria-busy={loading || undefined}>
            {shown.map((c) => <TestCard key={c.id} card={c} lobby={`${base}/assessments/${c.id}`} primary={c.id === primaryId} />)}
          </ul>
        )}
        {error && items.length > 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} /> : null}
        <Pagination nextCursor={cursor} loading={loading} onLoadMore={() => void load(cursor)} />
      </section>
      <PracticeSection />
    </div>
  );
}

/** Step 3a S2 (D6): the «Тренировки» section at the end of the Тесты tab (`#practice`), when practice is published. */
function PracticeSection() {
  const { course } = useCourse();
  const shown = !!course.features?.practice;
  useEffect(() => {
    if (!shown || window.location.hash !== "#practice") return;
    const id = window.setTimeout(() => document.getElementById("practice")?.scrollIntoView(), 300);
    return () => window.clearTimeout(id);
  }, [shown]);
  if (!shown) return null;
  return (
    <section id="practice" className="scroll-mt-24 border-t border-slate-200 pt-6">
      <PracticeList embedded />
    </section>
  );
}

/** Step 3a S2 (§3.2, D4): the Тесты (or Задания) tab of a course that is not an exam course: its assignments as cards
 * in the library's grid (status, kind, due date, attempts, one primary action on the next one), then «Тренировки». */
function AssignmentsTab() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const errorText = useAssignmentErrorText();
  const base = `/${lang}/courses/${course.id}`;
  const [items, setItems] = useState<AssignmentStudentOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listAssignments(course.id, { cursor: next, limit: 50 });
      const rows = page.items as AssignmentStudentOut[];
      setItems((p) => (next ? [...p, ...rows] : rows));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id]);
  useEffect(() => { void load(); }, [load]);
  const rows = useMemo(() => {
    const now = Date.now();
    return sortForStudent(items).map((a) => ({ a, v: studentAssignmentView(a, now, false) }));
  }, [items]);
  const primaryId = primaryAssignmentId(rows);
  const title = course.features?.hand_ins ? t("course.tabs.assignments") : t("course.tabs.tests");
  return (
    <div className="space-y-6">
      <section className="min-w-0 space-y-5">
        <StudentPageHeader title={title} />
        {error && items.length === 0 ? <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} /> : null}
        {loading && items.length === 0 && !error && (
          <div role="status" aria-live="polite">
            <span className="sr-only">{t("ui.loading")}</span>
            <div aria-hidden="true" className={GRID}>{[0, 1, 2].map((i) => <Skeleton key={i} className="h-44 w-full rounded-card" />)}</div>
          </div>
        )}
        {!loading && !error && items.length === 0 && (
          <EmptyState mascot="reading" icon={<ClipboardList />} title={t("assignments.student.empty")} description={t("assignments.student.emptyHint")} />
        )}
        {rows.length > 0 && (
          <ul className={cn(GRID, "[&>li]:flex [&>li]:flex-col")}>
            {rows.map(({ a, v }) => (
              <StudentAssignmentCard key={a.id} a={a} v={v} base={base} primary={a.id === primaryId}
                title={pickLocalized(a.title, lang, course.default_language) || t("assignments.untitled")} />
            ))}
          </ul>
        )}
        {error && items.length > 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} /> : null}
        <Pagination nextCursor={cursor} loading={loading} onLoadMore={() => void load(cursor)} />
      </section>
      <PracticeSection />
    </div>
  );
}

/** `/courses/{c}/tests`: the Тесты tab. Students of an exam-prep course get the library, students of any other course
 * (step 3a S2) their assignments; anyone else goes to the course page. */
export function TestsPage() {
  const { lang } = useTranslation();
  const router = useRouter();
  const { course } = useCourse();
  const examPrep = course.my_enrollment.role === "student" && templateUi(course).studentLayout === "exam_prep";
  const general = !examPrep && inCourseSpace(course);
  useEffect(() => {
    if (!examPrep && !general) router.replace(`/${lang}/courses/${course.id}`);
  }, [examPrep, general, lang, course.id, router]);
  if (general) return <AssignmentsTab />;
  if (!examPrep) return <TestsSkeleton />;
  return <TestsLibrary />;
}
